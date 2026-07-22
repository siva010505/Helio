"""
Phase 6 Smoke Test.
Tests SEOAgent and ThumbnailAgent.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import json
from dotenv import load_dotenv
load_dotenv()

from src.config_loader import load_config
from src.llm_client import LLMClient
from src.agents.seo_agent import SEOAgent
from src.agents.thumbnail_agent import ThumbnailAgent

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    config = load_config()
    llm = LLMClient(model=config["llm"]["model"], vision_model=config["llm"]["vision_model"], temperature=config["llm"]["temperature"])
    ch_cfg = config["channels"][0]

    script_text = "AI is incredible. Robots learn very fast. The future is here!"
    topic_text = "The rapid evolution of Artificial Intelligence and Robotics."

    print("\n[TEST] 1. Generating SEO Metadata...")
    seo = SEOAgent(llm)
    metadata = seo.generate_metadata(script_text, topic_text, ch_cfg)
    
    print("\n--- METADATA ---")
    print(f"Title: {metadata.get('title')}")
    print(f"Description: {metadata.get('description')}")
    print(f"Tags: {metadata.get('tags')}")
    
    assert metadata.get('title'), "Title is missing"
    assert metadata.get('description'), "Description is missing"
    assert metadata.get('tags'), "Tags are missing"

    print("\n[TEST] 2. Generating Thumbnail...")
    # Use the fallback visual as a mock video
    video_path = "assets/fallback_visual.mp4"
    if not os.path.exists(video_path):
        print(f"Skipping thumbnail test as {video_path} does not exist.")
    else:
        thumbnailer = ThumbnailAgent(ch_cfg)
        thumb_path = thumbnailer.generate_thumbnail(video_path, metadata['title'], 9997)
        print(f"Thumbnail saved to: {thumb_path}")
        assert os.path.exists(thumb_path), "Thumbnail not generated!"

    print("\n=======================================================")
    print("  Phase 6 Smoke Test: ALL CHECKS PASSED")
    print("=======================================================")

if __name__ == "__main__":
    main()
