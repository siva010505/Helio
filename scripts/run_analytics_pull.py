import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config_loader import load_config
from src.db.db import SessionLocal
from src.agents.analyst_agent import AnalystAgent
from src.llm_client import LLMClient

def main():
    config = load_config()
    db = SessionLocal()
    llm = LLMClient(
        model=config['llm']['model'],
        vision_model=config['llm']['vision_model'],
        temperature=config['llm']['temperature']
    )
    analyst = AnalystAgent(llm, config, db)
    analyst.run_analysis()
    db.close()

if __name__ == "__main__":
    main()
