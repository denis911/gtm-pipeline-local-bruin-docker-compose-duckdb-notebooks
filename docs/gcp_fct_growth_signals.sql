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
    `{{ var.project_id }}.{{ var.dataset_name }}.ext_github_signals`
WHERE 
    DATE(created_at) = '{{ BRUIN_START_DATE | default('2026-03-19') }}'
GROUP BY 1, 2, 3, 4, 5
