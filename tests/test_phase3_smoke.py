"""
Phase 3 Smoke Test.
Tests ScriptAgent and VoiceAgent using a mock topic.
Requires internet connection for Piper ONNX model download.
Uses real API keys for LLM Script Generation.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import json
from dotenv import load_dotenv
load_dotenv()

from src.config_loader import load_config
from src.db.db import SessionLocal
from src.db.models import Channel, Topic, Video
from src.llm_client import LLMClient
from src.agents.script_agent import ScriptAgent
from src.agents.voice_agent import VoiceAgent

def main():
    config = load_config()
    db = SessionLocal()
    llm = LLMClient(
        model=config["llm"]["model"],
        vision_model=config["llm"]["vision_model"],
        temperature=config["llm"]["temperature"]
    )
    
    ch_cfg = config["channels"][0]
    
    print("[TEST] Fetching/Creating Channel in DB...")
    channel = db.query(Channel).filter(Channel.name == ch_cfg["name"]).first()
    if not channel:
        channel = Channel(name=ch_cfg["name"], niche=ch_cfg["niche"], config_json=json.dumps(ch_cfg))
        db.add(channel)
        db.commit()

    topic_dict = {
        "channel_id": channel.id,
        "topic_text": "The incredible rise of autonomous AI coding agents",
        "description": "AI coding agents like Devin and others are changing how software is built.",
    }

    print("[TEST] Starting ScriptAgent...")
    script_agent = ScriptAgent(llm, db)
    script_data = script_agent.generate_script(topic_dict, ch_cfg)
    
    print("\n--- GENERATED SCRIPT ---")
    print(f"Hook: {script_data.get('hook')}")
    print(f"Full Script: {script_data.get('full_script')}")
    print("------------------------\n")
    
    assert script_data.get('full_script'), "Full script must not be empty"
    
    print("[TEST] Starting VoiceAgent...")
    voice_agent = VoiceAgent(ch_cfg)
    # Using 9999 as a dummy video ID
    audio_path = voice_agent.generate_voice(script_data.get("full_script"), ch_cfg.get("voice"), 9999)
    
    print(f"[PASS] Voice generation complete. Audio saved to: {audio_path}")
    assert os.path.exists(audio_path), "Audio file was not created"
    
    db.close()
    print("=" * 55)
    print("  Phase 3 Smoke Test: ALL CHECKS PASSED")
    print("=" * 55)

if __name__ == "__main__":
    main()
