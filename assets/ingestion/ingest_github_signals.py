"""@bruin
name: raw.github_signals
type: python
image: python:3.13
connection: duckdb-default

materialization:
  type: table
  strategy: merge

columns:
  - name: signal_date
    type: date
    primary_key: true
  - name: repo_name
    type: varchar
    primary_key: true
  - name: actor_login
    type: varchar
    primary_key: true
  - name: repo_url
    type: varchar
  - name: event_type
    type: varchar
  - name: created_at
    type: timestamp
  - name: ingestion_date
    type: date
@bruin"""

import gzip
import json
import os
import requests
from datetime import datetime
from typing import List

import pandas as pd


def get_tech_keywords(csv_path: str) -> List[str]:
    """Extract tech keywords from structured_jobs.csv"""
    import ast
    
    df = pd.read_csv(csv_path)
    # Extract unique keywords from tech_stack column
    keywords = set()
    for _, row in df.iterrows():
        if 'tech_stack' in row and pd.notna(row['tech_stack']):
            tech_stack_str = str(row['tech_stack'])
            try:
                # Try to parse as Python list
                techs = ast.literal_eval(tech_stack_str)
                if isinstance(techs, list):
                    for tech in techs:
                        tech = str(tech).strip().lower()
                        if tech and len(tech) > 1:
                            keywords.add(tech)
                else:
                    # Fallback: split by common delimiters
                    techs = tech_stack_str.replace('/', ',').replace(';', ',').split(',')
                    for tech in techs:
                        tech = tech.strip().lower()
                        if tech and len(tech) > 1 and tech not in ['[', ']', "'", '"']:
                            keywords.add(tech)
            except (ValueError, SyntaxError):
                # Fallback: split by common delimiters
                techs = tech_stack_str.replace('/', ',').replace(';', ',').split(',')
                for tech in techs:
                    tech = tech.strip().lower()
                    if tech and len(tech) > 1 and tech not in ['[', ']', "'", '"']:
                        keywords.add(tech)
    return list(keywords)


def download_github_archive_hour(session: requests.Session, date_str: str, hour: int) -> List[dict]:
    """Download and parse GitHub Archive JSON for a given date and hour."""
    url = f"https://data.githubarchive.org/{date_str}-{hour}.json.gz"
    
    try:
        response = session.get(url, timeout=30)
        if response.status_code == 404:
            # Common for "today" - ignore gracefully
            return []
            
        response.raise_for_status()
        
        # Decompress gzip
        content = gzip.decompress(response.content)
        
        # Parse JSON lines
        events = []
        for line in content.decode('utf-8').strip().split('\n'):
            if line:
                events.append(json.loads(line))
        
        return events
        
    except Exception as e:
        print(f"  ![Hour {hour}] Error: {e}")
        return []


def materialize():
    """
    Main function called by Bruin.
    Downloads GitHub events for ALL 24 hours of the target date.
    Returns a combined DataFrame for idempotence and upsert.
    """
    # Get target date from environment (Bruin's default, or Docker's PIPELINE_DATE)
    target_date = os.environ.get('BRUIN_START_DATE') or os.environ.get('PIPELINE_DATE', '2026-03-19')
    
    print(f"🚀 Starting FULL DAY ingestion (24 hours) for: {target_date}")
    
    # Load tech keywords
    keywords = get_tech_keywords('structured_jobs.csv')
    print(f"📍 Loaded {len(keywords)} tech keywords for filtering...")
    
    all_filtered_events = []
    total_raw_events = 0

    # Use a session for efficient multi-hour downloads
    with requests.Session() as session:
        for hour in range(24):
            print(f"  [{hour:02d}/23] Fetching hour {hour}...", end='\r')
            
            hourly_events = download_github_archive_hour(session, target_date, hour)
            if not hourly_events:
                continue
                
            total_raw_events += len(hourly_events)
            
            # Filter for WatchEvent (Stars)
            for event in hourly_events:
                try:
                    if event.get('type') != 'WatchEvent':
                        continue
                        
                    repo_name = event.get('repo', {}).get('name', '')
                    repo_name_lower = repo_name.lower()
                    
                    if any(kw in repo_name_lower for kw in keywords):
                        all_filtered_events.append({
                            'signal_date': target_date,
                            'repo_name': repo_name,
                            'repo_url': event.get('repo', {}).get('url', ''),
                            'actor_login': event.get('actor', {}).get('login', ''),
                            'created_at': event.get('created_at', ''),
                            'event_type': 'WatchEvent',
                            'ingestion_date': datetime.now().date()
                        })
                except:
                    continue
            
            # Clean up memory per hour
            del hourly_events

    print(f"\n✅ Finished processing 24 hours.")
    print(f"📊 Summary:")
    print(f"  - Total events scanned: {total_raw_events:,}")
    print(f"  - Matching signals found: {len(all_filtered_events):,}")
    
    # Convert to DataFrame
    df = pd.DataFrame(all_filtered_events)
    
    if not df.empty:
        df['created_at'] = pd.to_datetime(df['created_at'])
        df['signal_date'] = pd.to_datetime(df['signal_date']).dt.date
        df['ingestion_date'] = pd.to_datetime(df['ingestion_date']).dt.date
    else:
        return pd.DataFrame(columns=[
            'signal_date', 'repo_name', 'repo_url', 'actor_login',
            'created_at', 'event_type', 'ingestion_date'
        ])
    
    return df
