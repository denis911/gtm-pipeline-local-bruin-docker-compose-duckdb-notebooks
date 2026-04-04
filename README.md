# GitHub Signals Pipeline - Local Bruin + DuckDB

A data pipeline that downloads GitHub events (stars/watches) from [GitHub Archive](https://www.ghtorrent.org/) and stores them locally in DuckDB for analysis. Designed to run on Windows 11 using Docker Compose.

## 🎯 What This Pipeline Does

1. **Downloads** GitHub events for a specific date from GitHub Archive
2. **Filters** for `WatchEvent` (GitHub stars) matching tech keywords from `structured_jobs.csv`
3. **Stores** results in `local_data.duckdb` using idempotent upserts
4. **Aggregates** signals into a fact table for analysis

11. **Analyze** data locally using Jupyter Notebooks in the `notebooks/` folder.
12. **Automatic Isolation**: Designed to run cleanly even when shared between Windows host and Docker Linux.

---

## 📋 Prerequisites

### Required Software

| Software | Version | Download |
|----------|---------|----------|
| Docker Desktop | 4.0+ | [docker.com](https://www.docker.com/products/docker-desktop/) |
| Git Bash | Any recent | [git-scm.com](https://git-scm.com/download/win) |
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) (optional, for local testing) |

### Check Installation

Open **Git Bash** and verify:

```bash
# Check Docker
docker --version
# Expected: Docker version 24.x.x or similar

# Check Docker Compose
docker compose version
# Expected: Docker Compose version v2.x.x or similar

# Verify Docker is running
docker ps
# Expected: Should show headers with no errors
```

---

## 🚀 Quick Start

### Step 1: Clone the Repository

```bash
git clone https://github.com/denis911/gtm-pipeline-local-bruin-docker-compose-duckdb-notebooks.git
cd gtm-pipeline-local-bruin-docker-compose-duckdb-notebooks
```

### Step 2: Start Docker Desktop

1. Open **Docker Desktop** from Start Menu
2. Wait for the whale icon in the system tray to stop animating
3. Green/white whale in tray = Docker is running ✅

### Step 3: Validate the Pipeline

```bash
# In Git Bash, run:
docker compose run --rm bruin bruin validate .
```

**Expected output:**
```
✅ Validation passed
```

If you see errors, see [Debugging](#-debugging) section below.

### Step 4: Run the Pipeline

The pipeline downloads GitHub events for a specific date. 

**Run with the built-in reference date (2026-03-19)**:

```bash
docker compose run --rm bruin bruin run .
```

(NB: it takes about 5 mins to download data for 1 day)

You will see something similar in the console:
```bash
[07:12:07] [raw.github_signals] >> 🚀 Starting FULL DAY ingestion (24 hours) for: 2026-03-19
[07:12:08] [raw.github_signals] >> 📍 Loaded 269 tech keywords for filtering...
  [23/23] Fetching hour 23...s] >>   [00/23] Fetching hour 0...
[07:16:15] [raw.github_signals] >> ✅ Finished processing 24 hours.     
[07:16:15] [raw.github_signals] >> 📊 Summary:
[07:16:15] [raw.github_signals] >>   - Total events scanned: 3,720,634  
[07:16:15] [raw.github_signals] >>   - Matching signals found: 16,803   
[07:16:15] [raw.github_signals] Successfully collected the data from the asset, uploading to the destination...
[07:16:24] [raw.github_signals] Successfully loaded the data from the asset into the destination.
[07:16:24] Finished: raw.github_signals (4m35.826s) 
```

*Note: We have pre-configured this date 2026-03-19 in `docker-compose.yml` to make first-run tests easier and reproducible.*

**Or run for a specific date:**
```bash
docker compose run --rm bruin bruin run . --start-date 2026-03-20
```

### Step 5: Analyze the Results (Notebooks)

Since we fixed the local `uv` environment on Windows, you can run the analytics notebook directly on your machine:

```bash
# 1. Start the notebook server
uv run jupyter notebook notebooks/gtm_signals_analysis.ipynb
```

This will open a browser where you can query the `data/local_data.duckdb` file produced by Docker.

### Step 6: Visual Exploration (Optional)

If you prefer a database IDE, you can use the DuckDB web UI - usually available at `http://localhost:4213` or opens automatically in a new browser window:

```bash
duckdb -ui data/local_data.duckdb
```

In the DuckDB notebook:

```sql
-- Check raw signals table
SELECT signal_date, COUNT(*) as count FROM raw.github_signals GROUP BY signal_date;

-- Check aggregated signals
SELECT * FROM fct_growth_signals LIMIT 10;

-- Exit DuckDB
.exit
.quit
```

---

## 📁 Project Structure

```
├── .bruin.yml                    # Bruin connection configuration
├── docker-compose.yml            # Docker Compose configuration
├── pipeline.yml                  # Pipeline settings (ROOT - Bruin requirement)
├── assets/                       # Pipeline assets
│   ├── ingestion/
│   │   └── ingest_github_signals.py  # Downloads & filters GitHub data
│   └── staging/
│       └── fct_growth_signals.sql     # Aggregates signals
├── data/
│   └── local_data.duckdb         # Local database (persistence)
├── notebooks/
│   └── gtm_signals_analysis.ipynb # Analysis & viz
├── structured_jobs.csv           # Tech keywords source
└── README.md                    # This file
```

**Important:** `pipeline.yml` MUST be in the project root (not in a subfolder) for Bruin to find it.

---

## 🔧 Configuration Files Explained

### `.bruin.yml` - Connection Settings

This file tells Bruin how to connect to DuckDB:

```yaml
default_environment: default

environments:
  default:
    connections:
      duckdb:
        - name: "duckdb-default"
          path: "./data/local_data.duckdb"
```

- `path`: Location of your DuckDB file (relative to project root)
- The DuckDB file is created automatically on first run

### `pipeline.yml` - Pipeline Settings (in root folder)

```yaml
name: github-signals-pipeline
schedule: daily
start_date: "2026-03-01"

default_connections:
  duckdb: duckdb-default

variables:
  target_date:
    type: string
    default: "2026-03-19"
```

- `schedule`: How often to run (`daily`, `hourly`, etc.)
- `start_date`: When the pipeline starts tracking data
- `variables`: Parameters that can be overridden

### Environment Variables

You can set these in a `.env` file (create if not exists):

```bash
# .env file
PIPELINE_DATE=2026-03-19
BRUIN_LOG_LEVEL=INFO
```

---

## 🐳 Docker Compose Commands

### Basic Commands

```bash
# Validate pipeline (check for errors)
docker compose run --rm bruin bruin validate .

# Run for a specific date (choose ONE method below)
docker compose run --rm bruin bruin run . --start-date 2026-03-19
# OR via environment variable:
docker compose run --rm -e PIPELINE_DATE=2026-03-19 bruin bruin run .

# Run for a date range
docker compose run --rm bruin bruin run . --start-date 2026-03-01 --end-date 2026-03-31

# Run with full refresh (reprocess all data)
docker compose run --rm bruin bruin run . --full-refresh

# Run specific asset only
docker compose run --rm bruin bruin run . --select raw.github_signals
```

### Cleanup Commands

```bash
# Stop and remove containers
docker compose down

# Remove all containers, volumes, and images (careful!)
docker compose down -v --rmi all

# Remove the DuckDB file to start fresh
rm data/local_data.duckdb
```

---

## 🔍 Debugging

### Viewing Logs

```bash
# Follow logs in real-time (run in separate terminal)
docker compose logs -f

# View last 100 lines
docker compose logs --tail=100

# Save logs to file
docker compose logs > pipeline.log 2>&1

# View only errors
docker compose logs | grep -i error
```

### Testing Individual Components

```bash
# Test GitHub Archive download
docker compose run --rm bruin bash -c "curl -s https://data.githubarchive.org/2026-03-19-0.json.gz | gunzip | head -1"

# Test DuckDB connection
docker compose run --rm bruin duckdb data/local_data.duckdb -c "SELECT 1;"

# List all tables
docker compose run --rm bruin duckdb data/local_data.duckdb -c "SHOW TABLES;"

# Check table schema
docker compose run --rm bruin duckdb data/local_data.duckdb -c "DESCRIBE raw.github_signals;"
```

### Inspect Docker Container

```bash
# List running containers
docker ps

# List all containers (including stopped)
docker ps -a

# Open bash in the container
docker compose run --rm bruin bash

# Check container logs for specific service
docker compose logs bruin --tail=50
```

---

## 📊 Query Examples

Connect to DuckDB and run these queries:

```bash
docker compose run --rm bruin duckdb local_data.duckdb
```

### Basic Queries

```sql
-- Total signals by date
SELECT signal_date, COUNT(*) as total_signals
FROM raw.github_signals
GROUP BY signal_date
ORDER BY signal_date DESC;

-- Top 20 starred repos
SELECT repo_name, COUNT(*) as stars
FROM raw.github_signals
WHERE event_type = 'WatchEvent'
GROUP BY repo_name
ORDER BY stars DESC
LIMIT 20;

-- Signals per hour
SELECT 
    DATE_TRUNC('hour', created_at) as hour,
    COUNT(*) as events
FROM raw.github_signals
GROUP BY 1
ORDER BY 1;
```

### Aggregated Signals

```sql
-- Growth signals by company
SELECT company_name, SUM(signal_count) as total_signals
FROM fct_growth_signals
GROUP BY company_name
ORDER BY total_signals DESC
LIMIT 10;

-- Intent priority distribution
SELECT intent_priority, COUNT(*) as repos
FROM fct_growth_signals
GROUP BY intent_priority;
```

### Verification Queries

```sql
-- Check for duplicate dates (idempotency test)
SELECT signal_date, COUNT(DISTINCT repo_name) as unique_repos
FROM raw.github_signals
GROUP BY signal_date
HAVING COUNT(*) > COUNT(DISTINCT repo_name);

-- Check ingestion history
SELECT DISTINCT ingestion_date, COUNT(*) as records
FROM raw.github_signals
GROUP BY ingestion_date;
```

---

## 🔄 Re-running the Pipeline

The pipeline is **idempotent** - you can run it multiple times for the same date without duplicating data.

```bash
# Re-run for March 19th (choose ONE method)
docker compose run --rm bruin bruin run . --date 2026-03-19
# OR via environment variable:
docker compose run --rm -e PIPELINE_DATE=2026-03-19 bruin bruin run .

# Run for multiple dates
for date in 2026-03-19 2026-03-20 2026-03-21; do
  docker compose run --rm bruin bruin run . --date $date
done
```

---

## 🧹 Reset & Troubleshooting

### Start Fresh

```bash
# Remove database and re-download all data
rm data/local_data.duckdb
docker compose run --rm bruin bruin run .
```

### Check Docker Resources

```bash
# Docker disk usage
docker system df

# Clean up unused images/containers
docker system prune -a

# Restart Docker Desktop (from system tray)
# Right-click Docker icon → Restart
```

### Verify GitHub Archive Data

GitHub Archive files are available at: `https://data.githubarchive.org/{YYYY-MM-DD}-{HH}.json.gz`

```bash
# Test if GitHub Archive is accessible
curl -I https://data.githubarchive.org/2026-03-19-0.json.gz
# Expected: HTTP/2 200
```

---

## 📚 Additional Resources

- [Bruin Documentation](https://docs.bruin.com/)
- [DuckDB Documentation](https://duckdb.org/docs/)
- [GitHub Archive](https://www.ghtorrent.org/)
- [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)

---

## 🆘 Getting Help

1. **Check logs:** `docker compose logs -f`
2. **Validate pipeline:** `docker compose run --rm bruin bruin validate .`
3. **Search existing issues** in the repository
4. **Create a new issue** with:
   - Docker version: `docker --version`
   - Docker Compose version: `docker compose version`
   - Full error message
   - Steps to reproduce

---

## 📝 Notes

- **Windows 11 limitation:** Bruin is blocked by Windows security policies locally, hence Docker is required
- **Data persistence:** `local_data.duckdb` is stored on your host machine, survives container restarts
- **Gitignored:** The DuckDB file is in `.gitignore` to avoid bloating the repo (grows with data)
- **Free data source:** GitHub Archive provides historical GitHub event data since 2011

---

*Last updated: 2026-04-03*
