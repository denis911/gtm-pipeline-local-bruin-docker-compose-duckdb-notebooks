"""@bruin
name: ingest_github_signals
type: python
image: ghcr.io/bruin-data/bruin-python-sdk:latest
@bruin"""

import os
import pandas as pd
# from google.cloud import bigquery
# from google.cloud import storage
# from google.cloud.bigquery import ExternalConfig
import logging
import ast

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_tech_keywords(csv_path: str) -> list[str]:
    df = pd.read_csv(csv_path)
    all_tech = []
    
    if 'tech_stack' in df.columns:
        for stack in df['tech_stack'].dropna():
            try:
                keywords = ast.literal_eval(stack)
                if isinstance(keywords, list):
                    all_tech.extend(keywords)
                else:
                    all_tech.append(str(keywords))
            except (ValueError, SyntaxError):
                all_tech.append(str(stack))
                
    unique_tech = sorted(list(set([t.strip().lower() for t in all_tech if t])))
    logger.info(f"Extracted {len(unique_tech)} unique tech keywords.")
    return unique_tech

def ingest_github_data(project_id: str, bucket_name: str, target_date: str):
    client = bigquery.Client(project=project_id)
    bq_date = target_date.replace("-", "")
    table_id = f"githubarchive.day.{bq_date}"
    
    import re
    keywords = get_tech_keywords("structured_jobs.csv")
    escaped_keywords = [re.escape(k) for k in keywords]
    regex_pattern = "|".join([rf"\b{k}\b" for k in escaped_keywords])
    
    query = f"""
    SELECT 
        repo.name as repo_name,
        repo.url as repo_url,
        actor.login as actor_login,
        created_at,
        type as event_type
    FROM `{table_id}`
    WHERE type = 'WatchEvent'
    AND REGEXP_CONTAINS(LOWER(repo.name), r'{regex_pattern}')
    LIMIT 10000
    """
    
    logger.info(f"Running query on {table_id}...")
    query_job = client.query(query)
    results = query_job.to_dataframe()
    
    if results.empty:
        logger.warning(f"No results found for {target_date} with current keywords.")
        return

    logger.info(f"Fetched {len(results)} rows. Saving to GCS...")
    results['ingestion_date'] = pd.to_datetime('today').date()
    results['signal_date'] = pd.to_datetime(target_date).date()
    
    local_path = "temp_signals.parquet"
    results.to_parquet(local_path, index=False)
    
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)
    gcs_path = f"raw/github_signals/date={target_date}/data.parquet"
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_path)
    os.remove(local_path)
    logger.info(f"Successfully uploaded to gs://{bucket_name}/{gcs_path}")

    # Create/Update BigQuery External Table
    dataset_id = os.getenv("BIGQUERY_DATASET", "gtm_intelligence_dwh")
    external_table_id = f"{project_id}.{dataset_id}.ext_github_signals"
    
    # Configure external table to point to ALL dates in the raw folder
    # This allows the SQL to filter by partition/date in the query
    source_uri = f"gs://{bucket_name}/raw/github_signals/*/data.parquet"
    
    table = bigquery.Table(external_table_id)
    external_config = ExternalConfig("PARQUET")
    external_config.source_uris = [source_uri]
    external_config.autodetect = True
    
    # Enable hive partitioning if the folder structure matches date=YYYY-MM-DD
    hive_partitioning = bigquery.HivePartitioningOptions()
    hive_partitioning.mode = "AUTO"
    hive_partitioning.source_uri_prefix = f"gs://{bucket_name}/raw/github_signals/"
    external_config.hive_partitioning = hive_partitioning
    
    table.external_data_configuration = external_config
    
    try:
        client.delete_table(external_table_id, not_found_ok=True)
        client.create_table(table)
        logger.info(f"Successfully created/updated external table {external_table_id}")
    except Exception as e:
        logger.error(f"Failed to create external table: {e}")

if __name__ == "__main__":
    # project_id = os.getenv("GCP_PROJECT_ID", "evident-axle-339820")
    # bucket_name = os.getenv("DATA_LAKE_BUCKET", f"{project_id}-data-lake")
    target_date = "2026-03-19"
    
    ingest_github_data(project_id, bucket_name, target_date)
