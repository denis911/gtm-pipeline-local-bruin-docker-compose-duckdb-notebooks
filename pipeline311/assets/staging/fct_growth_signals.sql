/* @bruin
name: fct_growth_signals
type: duckdb.sql
connection: duckdb-default

materialization:
  type: table
  strategy: append

depends:
  - raw.github_signals
@bruin */

SELECT
    signal_date,
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
