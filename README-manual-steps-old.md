# Old README - manual steps to start the project

## Setting up local pipeline

For GIT BASH use
```Terminal: Select Default Profile```
and select `Git Bash`

For running uv use

```bash
uv init
uv venv
uv sync
```

For duckdb use

```bash
uv add duckdb
```

For bruin use

```bash
uv add bruin
```

and init bruin project as follows:

```bash
uv run bruin init
```

NB! Structure for single Bruin project per repo (most common):

```
repo-root/
├── bruin.yaml
├── pipelines/
└── ...
```

In default case we start with chess players dataset pipeline, like so:

```bash
uv run bruin init default .
```

but in our case specifically we use NY taxi dataset pipeline:

```bash
uv run bruin init zoomcamp .
```

then check with:
```bash
uv run bruin validate .
``` 

and finally run with:
```bash
uv run bruin run .
``` 

As a result a new duckdb flie is created - `duckdb.db`
Run the following to check the contents of the duckdb file:
```bash
duckdb -ui duckdb.db
``` 

and see what is inside - for chess players dataset it coul be:

```sql
SELECT name, count(*) AS player_count
FROM dataset.players
GROUP BY 1
```

## Running the pipeline

After full pileline is ready we can download 1 year worth of data:

```bash
uv run bruin run \
   --start-date 2022-01-01 \   
   --end-date 2023-01-01 \   
   --full-refresh \
   --environment default \
   "c:\tmp\antigravity-bruin-mcp-bigquery\zoomcamp\pipeline\pipeline.yml"
```

Or adapted to my win 11 PC:

```bash
 uv run bruin run --start-date 2022-01-01 --end-date 2023-01-01   --full-refresh --environment default "c:\tmp\antigravity-bruin-mcp-bigquery\zoomcamp\pipeline\pipeline.yml"
```

NB - if I try to run it without UV - like `bruin run` - it will crush due
to win 11 security policies. 

To check the contents of the duckdb file - it has 12 months of data, 2.2 GB in size:
```bash
duckdb -ui duckdb.db
``` 

and run SQL query:
```sql
from duckdb.ingestion.trips
select count(*)
-- 42722864 rows for 12 months
```

In aggregated table we should have 365 rows (1 per each day of 2022):
```sql
from duckdb.reports.trips_report
select count(*)
-- 365 rows
``` 
-- as we have aggregated revenue and trip distance per day.

We may also check which year/months were aggregated: 
```sql
from duckdb.reports.trips_report
select  year(pickup_date),
   month(pickup_date),
   sum(total_revenue) as revenue_per_month
group by 1, 2
-- 12 months in 2022, total revenue per month
``` 
