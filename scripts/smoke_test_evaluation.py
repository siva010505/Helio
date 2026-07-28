import sys
import os
import json
from datetime import datetime, timedelta

# Allow imports from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from src.db.db import SessionLocal
from src.db.models import Channel, Video, PerformanceMetric, PromptVersion
from src.llm_client import LLMClient
from src.agents.evaluation_agent import EvaluationAgent

def run_smoke_test():
    db = SessionLocal()
    
    # 1. Ensure channel exists or get first
    channel = db.query(Channel).first()
    if not channel:
        print("No channel found. Create a channel first!")
        return
        
    print(f"Using channel: {channel.name}")
    
    # Fake data pattern: 
    # - "story" hooks get amazing retention (90-95%)
    # - "question" hooks get terrible retention (30-40%)
    
    fake_videos = []
    fake_metrics = []
    
    # Get max prompt version ID before we start so we can clean up cleanly
    start_pv = db.query(PromptVersion).order_by(PromptVersion.id.desc()).first()
    max_pv_id = start_pv.id if start_pv else 0
    
    upload_date = datetime.utcnow() - timedelta(days=10)
    
    # Create 3 GOOD videos
    for i in range(3):
        v = Video(
            channel_id=channel.id,
            title=f"Fake Good Video {i}",
            hook_style="story",
            youtube_video_id=f"fake_good_{i}",
            upload_time=upload_date,
            status="uploaded"
        )
        db.add(v)
        db.flush()
        fake_videos.append(v)
        
        m = PerformanceMetric(
            video_id=v.id,
            pulled_at=datetime.utcnow(),
            views=5000,
            average_view_duration=45.0,
            average_view_percentage=92.0,
            ctr=8.5
        )
        db.add(m)
        fake_metrics.append(m)
        
    # Create 3 BAD videos
    for i in range(3):
        v = Video(
            channel_id=channel.id,
            title=f"Fake Bad Video {i}",
            hook_style="question",
            youtube_video_id=f"fake_bad_{i}",
            upload_time=upload_date,
            status="uploaded"
        )
        db.add(v)
        db.flush()
        fake_videos.append(v)
        
        m = PerformanceMetric(
            video_id=v.id,
            pulled_at=datetime.utcnow(),
            views=1000,
            average_view_duration=15.0,
            average_view_percentage=35.0,
            ctr=2.1
        )
        db.add(m)
        fake_metrics.append(m)
        
    db.commit()
    print("Injected 6 fake videos and metrics into DB.")
    
    try:
        # Run Evaluation Agent
        print("Running EvaluationAgent...")
        llm = LLMClient()
        # Mock config
        config = {
            "learning": {"min_videos_before_adjusting": 5},
            "channels": [{"name": channel.name, "db_id": channel.id}]
        }
        agent = EvaluationAgent(llm, db, config)
        
        result = agent.run_evaluation()
        print("\n=== EVALUATION RESULT ===")
        print(json.dumps(result, indent=2))
        
        print("\n=== NEW PROMPT VERSIONS SAVED ===")
        new_versions = db.query(PromptVersion).filter(PromptVersion.id > max_pv_id).all()
        for pv in new_versions:
            print(f"Agent: {pv.agent_name} | v{pv.version_number}")
            print(f"Prompt Update: {pv.prompt_text}\n")
            
    finally:
        # Cleanup
        print("\nCleaning up fake data...")
        for m in fake_metrics:
            db.delete(m)
        for v in fake_videos:
            db.delete(v)
            
        new_pvs = db.query(PromptVersion).filter(PromptVersion.id > max_pv_id).all()
        for pv in new_pvs:
            db.delete(pv)
            
        db.commit()
        print("Cleanup complete!")
        db.close()

if __name__ == "__main__":
    run_smoke_test()
