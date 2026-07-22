import sys
import os
import argparse
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config_loader import load_config
from src.db.db import SessionLocal
from src.pipeline import run_pipeline

def main():
    parser = argparse.ArgumentParser(description="Run the Helio pipeline in dry-run mode.")
    parser.add_argument("--channel", default="ai_news_shorts", help="Channel name to run")
    args = parser.parse_args()

    config = load_config()
    db = SessionLocal()
    
    # In a real dry-run, we might still need to select a topic or pass a dummy topic.
    # TODO: Implement dry-run orchestration calling run_pipeline with dry_run=True.
    
    db.close()

if __name__ == "__main__":
    main()
