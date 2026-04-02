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


def download_github_archive(date_str: str) -> List[dict]:
    """Download and parse GitHub Archive JSON for a given date."""
    # Format: 2026-03-19 -> 2026-03-19-0.json.gz (hour 0)
    # GitHub Archive files are hourly, but we can get all hours for simplicity
    url = f"https://data.githubarchive.org/{date_str}-0.json.gz"
    
    print(f"Downloading GitHub Archive from: {url}")
    
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        # Decompress gzip
        content = gzip.decompress(response.content)
        
        # Parse JSON lines
        events = []
        for line in content.decode('utf-8').strip().split('\n'):
            if line:
                events.append(json.loads(line))
        
        print(f"Downloaded {len(events)} events")
        return events
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading GitHub Archive: {e}")
        return []


def materialize():
    """
    Main function called by Bruin.
    Downloads GitHub events and filters for tech-related star events.
    Returns a DataFrame that Bruin will upsert into DuckDB.
    """
    # Get target date from environment or use default
    target_date = os.environ.get('BRUIN_START_DATE', '2026-03-19')
    
    print(f"Starting GitHub signals ingestion for date: {target_date}")
    
    # Load tech keywords
    keywords = get_tech_keywords('structured_jobs.csv')
    print(f"Loaded {len(keywords)} tech keywords")
    
    # Download GitHub Archive data
    events = download_github_archive(target_date)
    
    if not events:
        print("No events downloaded, returning empty DataFrame")
        return pd.DataFrame(columns=[
            'signal_date', 'repo_name', 'repo_url', 'actor_login',
            'created_at', 'event_type', 'ingestion_date'
        ])
    
    # Filter for WatchEvent (GitHub stars) matching tech keywords
    filtered_events = []
    for event in events:
        try:
            event_type = event.get('type', '')
            if event_type != 'WatchEvent':
                continue
            
            repo = event.get('repo', {})
            repo_name = repo.get('name', '')
            
            # Check if any keyword matches in repo name
            repo_name_lower = repo_name.lower()
            if any(kw in repo_name_lower for kw in keywords):
                filtered_events.append({
                    'signal_date': target_date,
                    'repo_name': repo_name,
                    'repo_url': repo.get('url', ''),
                    'actor_login': event.get('actor', {}).get('login', ''),
                    'created_at': event.get('created_at', ''),
                    'event_type': event_type,
                    'ingestion_date': datetime.now().date()
                })
        except Exception as e:
            # Skip malformed events
            continue
    
    print(f"Filtered to {len(filtered_events)} matching WatchEvents")
    
    # Convert to DataFrame
    df = pd.DataFrame(filtered_events)
    
    if not df.empty:
        # Ensure correct types
        df['created_at'] = pd.to_datetime(df['created_at'])
        df['signal_date'] = pd.to_datetime(df['signal_date']).dt.date
        df['ingestion_date'] = pd.to_datetime(df['ingestion_date']).dt.date
    
    return df
