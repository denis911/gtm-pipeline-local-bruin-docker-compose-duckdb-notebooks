# Migration Plan: GCP to Local Docker + DuckDB

## Overview

This document outlines the changes required to migrate the Bruin pipeline from GCP (BigQuery + GCS) to a local Docker-based setup using DuckDB for storage. The goal is to read GitHub data and store it locally in `local_data.duckdb` instead of BigQuery and GCS buckets.

---

## Current Architecture (GCP)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GCP (Current)                               │
│                                                                     │
│  ┌─────────────────┐      ┌──────────────────┐      ┌───────────┐  │
│  │ BigQuery        │      │ Google Cloud     │      │ GitHub    │  │
│  │ GitHubArchive   │ ───► │ Storage (GCS)    │ ───► │ Archive   │  │
│  │ (Source Data)   │      │ (Parquet Files)  │      │ Day Table │  │
│  └─────────────────┘      └──────────────────┘      └───────────┘  │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ BigQuery External Table (ext_github_signals)                 │  │
│  │ - Points to GCS bucket                                      │  │
│  │ - Uses hive partitioning (date=YYYY-MM-DD)                 │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Current Data Flow:
1. Query BigQuery GitHubArchive day table (e.g., `githubarchive.day.20260319`)
2. Filter for `WatchEvent` (GitHub stars) matching tech keywords from `structured_jobs.csv`
3. Save results as Parquet to GCS: `gs://{bucket}/raw/github_signals/date={date}/data.parquet`
4. Create/Update BigQuery external table pointing to GCS for downstream SQL queries

---

## Target Architecture (Local Docker + DuckDB)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Local Docker Container                          │
│                                                                     │
│  ┌─────────────────┐      ┌──────────────────┐      ┌───────────┐  │
│  │ DuckDB          │      │ Bruin Pipeline   │      │ GitHub    │  │
│  │ (local_data.    │ ◄─── │ (Python Asset)  │ ◄─── │ Archive   │  │
│  │  duckdb)        │      │                  │      │           │  │
│  └─────────────────┘      └──────────────────┘      └───────────┘  │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ DuckDB Tables                                                │   │
│  │ - raw.github_signals (upsert by signal_date)                │   │
│  │ - Jupyter notebooks for analysis                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Host Directory Mapping:                                           │
│  ./ (repo) ──────────────► /workspace (container)                 │
│  ./local_data.duckdb ──► Persisted on host                        │
└─────────────────────────────────────────────────────────────────────┘
```

### Target Data Flow:
1. Read tech keywords from `structured_jobs.csv`
2. Fetch GitHub data from GitHub Archive (https://data.githubarchive.org/)
3. Write results directly to DuckDB table `raw.github_signals` using UPSERT
4. Use Jupyter notebooks connected to DuckDB for data analysis

---

## User Decisions Incorporated

1. **GitHub Data Source**: GitHub Archive (SELECTED)
2. **Incremental Strategy**: UPSERT (idempotent - re-running same dates won't duplicate)
3. **Downstream SQL**: Jupyter Notebooks for ad-hoc analysis OR Bruin SQL assets
4. **Asset Organization**: Assets to be placed in `pipeline/` folder (Bruin standard)

## New: Second Pipeline Step - Aggregation SQL

User created `fct_growth_signals.sql` - A downstream aggregation step:

```sql
/* @bruin
name: gtm_intelligence_dwh.fct_growth_signals
type: bq.sql
materialization:
  type: table
  partition_by: signal_date
  cluster_by: ["company_name", "event_type"]
depends:
  - ingest_github_signals
@bruin */

SELECT
    DATE(created_at) as signal_date,
    SPLIT(repo_name, '/')[OFFSET(0)] as company_name, 
    repo_name,
    repo_url,
    event_type,
    COUNT(*) as signal_count,
    CASE 
        WHEN COUNT(*) > 100 THEN 'High'
        WHEN COUNT(*) > 10 THEN 'Medium'
        ELSE 'Low'
    END as intent_priority,
    CURRENT_TIMESTAMP() as processed_at
FROM 
    ...
WHERE 
    DATE(created_at) = '{{ BRUIN_START_DATE | default('2026-03-19') }}'
GROUP BY 1, 2, 3, 4, 5
```

**This needs conversion to DuckDB syntax:**
- `SPLIT(repo_name, '/')[OFFSET(0)]` → DuckDB uses `SPLIT_PART(repo_name, '/', 1)`
- Materialization settings need DuckDB equivalents
- BigQuery external table reference → direct DuckDB table reference

### DuckDB Version of fct_growth_signals.sql

```sql
/* @bruin
name: fct_growth_signals
type: duckdb.sql
materialization:
  type: table
depends:
  - ingest_github_signals
@bruin */

SELECT
    DATE(created_at) as signal_date,
    SPLIT_PART(repo_name, '/', 1) as company_name, 
    repo_name,
    repo_url,
    event_type,
    COUNT(*) as signal_count,
    CASE 
        WHEN COUNT(*) > 100 THEN 'High'
        WHEN COUNT(*) > 10 THEN 'Medium'
        ELSE 'Low'
    END as intent_priority,
    CURRENT_TIMESTAMP as processed_at
FROM 
    raw.github_signals
WHERE 
    signal_date = '{{ BRUIN_START_DATE | default('2026-03-19') }}'
GROUP BY 1, 2, 3, 4, 5
```

**Key differences from BigQuery:**
- `type: bq.sql` → `type: duckdb.sql`
- `SPLIT(...)[OFFSET(0)]` → `SPLIT_PART(..., '/', 1)`
- `CURRENT_TIMESTAMP()` → `CURRENT_TIMESTAMP` (DuckDB doesn't need parentheses)
- Table reference: BigQuery external table → DuckDB table `raw.github_signals`

## Organization Changes

- **Docs folder**: Documentation moved to `docs/` folder
  - `docs/README-bruin-full.md`
  - `docs/README-manual.md`
- **DuckDB file**: Added to `.gitignore` (file grows too large for Git)
- **Assets folder**: Suggested structure:
  ```
  pipeline/
  ├── pipeline.yml
  └── assets/
      ├── ingestion/
      │   └── ingest_github_signals.py
      └── staging/
          └── fct_growth_signals.sql
  ```

---

## Files to Modify

### 1. `ingest_github_signals.py` (MAJOR CHANGES)

**Current State:**
- Uses BigQuery client to query GitHubArchive
- Uses GCS client to upload Parquet files
- Creates BigQuery external tables

**Required Changes:**
- [ ] Remove BigQuery imports (`bigquery.Client`, `ExternalConfig`)
- [ ] Remove GCS imports (`storage.Client`, `bucket.blob`)
- [ ] Add DuckDB import for local storage
- [ ] Replace BigQuery query with GitHub Archive download
- [ ] Replace GCS upload with DuckDB UPSERT
- [ ] Add idempotent upsert logic using composite key
- [ ] Add table creation/upsert logic for DuckDB

### New Data Source: GitHub Archive

**Why GitHub Archive:**
- No API rate limits
- Historical data available back to 2011
- Free public dataset
- Format: JSON.gz files

**How it works:**
- Download daily files from: `https://data.githubarchive.org/`
- File naming: `2026-03-{01-31}.json.gz`
- Each file contains all GitHub events for that day
- Filter for `WatchEvent` (GitHub stars) matching tech keywords

**Reference Data (Test File):**
The test file `top-100-chart-2026-03-23T20-40-04.587Z.csv` contains:
- `company_name`: GitHub organization/user
- `signal_count`: Number of stars/watches
- `repo_name`: Full repo name (org/repo)

**Idempotency Test:**
- Same dates can be re-uploaded safely
- Uses `(signal_date, repo_name, actor_login)` as composite key for upserts

### 2. `.bruin.yml` (NEW or MODIFY)

**Current State:**
- Does not exist (gitignored)

**Required Changes:**
- [ ] Create `.bruin.yml` with DuckDB connection
- [ ] Configure `duckdb-default` connection pointing to `local_data.duckdb`
- [ ] Add environment configurations

**Example Structure:**
```yaml
environments:
  default:
    connections:
      duckdb:
        - name: duckdb-default
          database: local_data.duckdb
```

### 3. `docker-compose.yml` (MINOR CHANGES)

**Current State:**
- Already configured for Bruin
- Maps local directory to `/workspace`

**Suggested Enhancements:**
- [ ] Add named volume for DuckDB persistence
- [ ] Add environment variables for GitHub token
- [ ] Ensure `local_data.duckdb` is mapped to host directory

**Suggested Changes:**
```yaml
volumes:
  - .:/workspace                  # main project
  - ./local_data.duckdb:/workspace/local_data.duckdb  # DuckDB file
  - bruin_data:/data              # persistent volume for temp files

environment:
  - PIPELINE_DATE=${PIPELINE_DATE:-}
```

### 4. `structured_jobs.csv` (NO CHANGES)

**Current State:**
- Contains job postings with `tech_stack` column
- Keywords are extracted and used for filtering GitHub data

**Status:**
- No changes needed - continues to be the source of tech keywords

---

## New Files to Create

### 1. `pipeline/pipeline.yml` (NEW)

Bruin pipeline configuration defining the ingestion workflow.

**Content:**
```yaml
name: github-signals-pipeline
schedule: daily
start_date: "2026-03-01"

default_connections:
  duckdb: duckdb-default

variables:
  target_date:
    type: string
    default: "{{ env.PIPELINE_DATE | default('today') }}"
```

### 2. `.env.example` (NEW)

Example environment file.

**Content:**
```bash
# Pipeline date (optional, defaults to today)
PIPELINE_DATE=2026-03-19
```

---

## DuckDB Schema Design

### Table: `raw.github_signals`

```sql
CREATE TABLE IF NOT EXISTS raw.github_signals (
    repo_name VARCHAR,
    repo_url VARCHAR,
    actor_login VARCHAR,
    created_at TIMESTAMP,
    event_type VARCHAR,
    ingestion_date DATE,
    signal_date DATE,
    PRIMARY KEY (signal_date, repo_name, actor_login)
);
```

**Why this schema:**
- Matches the structure from BigQuery (repo_name, actor_login, created_at, event_type)
- `signal_date` identifies which day the data is from (for upsert logic)
- `ingestion_date` tracks when data was loaded (useful for debugging)
- Composite primary key enables idempotent upserts

### Upsert Strategy (Idempotent):

```python
# Pseudocode for upsert
INSERT INTO raw.github_signals (...)
VALUES (...)
ON CONFLICT (signal_date, repo_name, actor_login) 
DO UPDATE SET 
    repo_url = EXCLUDED.repo_url,
    created_at = EXCLUDED.created_at,
    event_type = EXCLUDED.event_type,
    ingestion_date = CURRENT_DATE;
```

**Test Case:**
- File: `top-100-chart-2026-03-23T20-40-04.587Z.csv`
- Expected behavior: Re-running pipeline for 2026-03-23 should NOT duplicate records

### Indexing:
```sql
CREATE INDEX idx_signal_date ON raw.github_signals (signal_date);
CREATE INDEX idx_repo_name ON raw.github_signals (repo_name);
CREATE UNIQUE INDEX idx_unique_signal ON raw.github_signals (signal_date, repo_name, actor_login);
```

---

## Jupyter Integration

Connect Jupyter to DuckDB for analysis:

```python
import duckdb
conn = duckdb.connect('local_data.duckdb')

# Query raw signals
df = conn.sql("""
    SELECT signal_date, repo_name, COUNT(*) as stars
    FROM raw.github_signals
    WHERE signal_date = '2026-03-23'
    GROUP BY signal_date, repo_name
    ORDER BY stars DESC
    LIMIT 100
""").df()
```

---

## Implementation Checklist

### Phase 1: Configuration
- [ ] Create `.bruin.yml` with DuckDB connection
- [ ] Update `docker-compose.yml` for persistence
- [ ] Create `.env.example` for pipeline date
- [ ] Add `.env` to `.gitignore`

### Phase 2: Core Asset Changes
- [ ] Rewrite `ingest_github_signals.py` for DuckDB
- [ ] Implement GitHub Archive download and parsing
- [ ] Implement idempotent UPSERT logic
- [ ] Test local DuckDB write
- [ ] Test idempotency with 2026-03-23 data

### Phase 3: Pipeline Integration
- [ ] Create `pipeline/pipeline.yml`
- [ ] Create `pipeline/assets/` structure
- [ ] Test Bruin run in Docker
- [ ] Verify DuckDB data persistence

### Phase 4: Jupyter & Analysis
- [ ] Create Jupyter notebook to connect to DuckDB
- [ ] Verify data matches `top-100-chart-2026-03-23T20-40-04.587Z.csv`
- [ ] Document query examples

---

## Reference: Original BigQuery Query

This is the query that generated the test file `top-100-chart-2026-03-23T20-40-04.587Z.csv`:

```sql
SELECT
  `company_name` AS `company_name`,
  `signal_count` AS `signal_count`,
  `repo_name` AS `repo_name`
FROM `evident-axle-339820`.`gtm_intelligence_dwh`.`fct_growth_signals`
WHERE
  TRUE
ORDER BY
  `signal_count` DESC
LIMIT 100
```

**Note:** This query reads from `fct_growth_signals` - a fact table that likely includes aggregation/transformation on top of the raw GitHub data. For DuckDB migration, we may need to either:
1. Store pre-aggregated data (like this query expects)
2. Or adapt the query to run aggregations on raw data in DuckDB

---

## DuckDB Query Examples

After migration, query the local data:

```bash
# Enter DuckDB CLI
docker compose run --rm bruin duckdb local_data.duckdb

# Or run DuckDB on host (if installed)
duckdb local_data.duckdb
```

```sql
-- Count signals by date
SELECT signal_date, COUNT(*) as signal_count
FROM raw.github_signals
GROUP BY signal_date
ORDER BY signal_date;

-- Top repositories by stars
SELECT repo_name, COUNT(*) as star_count
FROM raw.github_signals
WHERE event_type = 'WatchEvent'
GROUP BY repo_name
ORDER BY star_count DESC
LIMIT 20;

-- Tech keyword distribution
SELECT 
    COUNT(*) as total_signals,
    COUNT(DISTINCT repo_name) as unique_repos
FROM raw.github_signals
WHERE signal_date BETWEEN '2026-03-01' AND '2026-03-31';

-- Verify idempotency - should not increase on re-run
SELECT signal_date, COUNT(*) as total_records
FROM raw.github_signals
WHERE signal_date = '2026-03-23'
GROUP BY signal_date;
```

---

## Rollback Plan

If issues occur:
1. Keep original `ingest_github_signals.py` in a separate branch
2. Original GCP configuration can be restored
3. DuckDB data is stored locally and can be inspected manually

---

## Dependencies to Add

Update `pyproject.toml` or create `requirements.txt`:

```
# For DuckDB
duckdb>=1.5.1

# For GitHub Archive (downloading/parsing)
requests>=2.31.0
gzip (built-in)

# For JSON parsing
orjson>=3.9.0  # Faster JSON parsing for large files

# Already included
pandas>=3.0.2
```

---

## Notes

1. **GitHub Archive**: Daily files available at `https://data.githubarchive.org/2026-03-01.json.gz`

2. **Bruin Version**: The current `docker-compose.yml` uses `ghcr.io/bruin-data/bruin:latest`. Ensure this is compatible with DuckDB assets.

3. **Windows Path**: When mapping volumes in Docker on Windows, use absolute paths if relative paths cause issues.

4. **DuckDB vs duckdb.db**: The existing file is `local_data.duckdb`, not `duckdb.db`. Ensure Bruin and Docker configurations reference the correct filename.