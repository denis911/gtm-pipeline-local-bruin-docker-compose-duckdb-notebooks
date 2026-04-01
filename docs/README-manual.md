# Local Bruin Pipeline Setup (Windows 11)

## Prerequisites

- Docker Desktop installed and running
- Git Bash (for terminal)
- UV package manager

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repo
git clone <repo-url>
cd <repo-name>

# Initialize UV and sync dependencies
uv init
uv venv
uv sync
```

### 2. Configure DuckDB Connection (.bruin.yml)

Create `.bruin.yml` in the project root:

```yaml
default_environment: default

environments:
  default:
    connections:
      duckdb:
        - name: "duckdb-default"
          path: "./local_data.duckdb"
```

### 3. Configure Pipeline (pipeline.yml)

Create `pipeline/pipeline.yml`:

```yaml
name: github-signals-pipeline
schedule: daily
start_date: "2026-03-01"

default_connections:
  duckdb: "duckdb-default"

variables:
  target_date:
    type: string
    default: "{{ env.PIPELINE_DATE | default('today') }}"
```

## Running Bruin in Docker (Windows 11)

Windows 11 blocks Bruin locally, so run in Docker:

```bash
# 1. Validate pipeline
docker compose run --rm bruin bruin validate

# 2. Run pipeline for specific date
docker compose run --rm -e PIPELINE_DATE=2026-03-31 bruin bruin run . --date 2026-03-31

# 3. Run with date range
docker compose run --rm bruin bruin run . --start-date 2026-03-01 --end-date 2026-03-31
```

## Querying DuckDB

```bash
# Enter DuckDB CLI
docker compose run --rm bruin duckdb local_data.duckdb

# Or run locally (if DuckDB installed)
duckdb local_data.duckdb
```

Example queries:

```sql
-- Check raw signals
SELECT signal_date, COUNT(*) as count
FROM raw.github_signals
GROUP BY signal_date
ORDER BY signal_date DESC;

-- Top repos by stars
SELECT repo_name, COUNT(*) as stars
FROM raw.github_signals
WHERE event_type = 'WatchEvent'
GROUP BY repo_name
ORDER BY stars DESC
LIMIT 100;
```

## DuckDB SQL Asset Example

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
FROM raw.github_signals
WHERE signal_date = '{{ BRUIN_START_DATE | default('2026-03-19') }}'
GROUP BY 1, 2, 3, 4, 5
```

## DuckDB Python Asset Example

```python
"""@bruin
name: ingest_github_signals
type: python
image: ghcr.io/bruin-data/bruin-python-sdk:latest
@bruin"""

import duckdb
import pandas as pd
import gzip
import requests

def get_tech_keywords(csv_path: str) -> list[str]:
    df = pd.read_csv(csv_path)
    # ... extract keywords from tech_stack column
    
def download_github_archive(date: str) -> pd.DataFrame:
    url = f"https://data.githubarchive.org/{date}.json.gz"
    # ... download and parse JSON events
    
def ingest_github_data(target_date: str):
    conn = duckdb.connect('local_data.duckdb')
    
    # Create table if not exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw.github_signals (
            repo_name VARCHAR,
            repo_url VARCHAR,
            actor_login VARCHAR,
            created_at TIMESTAMP,
            event_type VARCHAR,
            ingestion_date DATE,
            signal_date DATE
        )
    """)
    
    # Download and process data
    events = download_github_archive(target_date)
    keywords = get_tech_keywords("structured_jobs.csv")
    
    # Filter for WatchEvent matching keywords
    # Insert with upsert logic
    # ...

if __name__ == "__main__":
    target_date = "2026-03-19"
    ingest_github_data(target_date)
```

## Notes

- DuckDB file (`local_data.duckdb`) is gitignored (grows too large)
- Pipeline uses GitHub Archive: https://data.githubarchive.org/
- Assets stored in `pipeline/assets/` folder
- Run `docker compose run --rm bruin bruin lineage .` to see asset dependencies

