import yaml
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))
from src.db.db import SessionLocal
from src.agents.analytics_agent import AnalyticsAgent
import logging

logging.basicConfig(level=logging.INFO)

print("Loading config...")
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

print("Starting AnalyticsAgent...")
db = SessionLocal()
agent = AnalyticsAgent(config, db)
results = agent.pull_metrics()
print(f"Pulled metrics for {len(results)} videos.")
