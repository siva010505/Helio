"""
Phase 5 Smoke Test.
Tests AssemblyAgent by stubbing the prior phases with minimal mock data.
Requires internet connection for Pexels API (downloading small video clips).
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import json
from dotenv import load_dotenv
load_dotenv()

from src.config_loader import load_config
from src.agents.voice_agent import VoiceAgent
from src.agents.caption_agent import CaptionAgent
from src.agents.visual_director_agent import VisualDirectorAgent
from src.agents.assembly_agent import AssemblyAgent
from src.llm_client import LLMClient

def main():
    config = load_config()
    ch_cfg = config["channels"][0]
    llm = LLMClient(model=config["llm"]["model"], vision_model=config["llm"]["vision_model"], temperature=config["llm"]["temperature"])

    script_text = "AI is incredible. Robots learn very fast."

    print("\n[TEST] 1. Preparing audio and captions...")
    voice_agent = VoiceAgent(ch_cfg)
    audio_path = voice_agent.generate_voice(script_text, ch_cfg.get("voice"), 9998)
    
    caption_agent = CaptionAgent(ch_cfg)
    words = caption_agent.generate_captions(audio_path)

    print("\n[TEST] 2. Mocking scenes and getting visual assets...")
    scenes = [
        {"scene_number": 1, "text_segment": "AI is incredible.", "search_query": "hacker typing", "description": "Hacker typing"},
        {"scene_number": 2, "text_segment": "Robots learn very fast.", "search_query": "robot factory", "description": "Robot factory"}
    ]
    director = VisualDirectorAgent(llm, config)
    final_scenes = director.select_visuals(scenes, words)

    print("\n[TEST] 3. Starting AssemblyAgent...")
    assembler = AssemblyAgent(ch_cfg)
    video_path = assembler.assemble_video(final_scenes, words, audio_path, 9998)
    
    print(f"\n[PASS] Video successfully assembled at: {video_path}")
    assert os.path.exists(video_path), "Final video file not found!"

    print("\n=======================================================")
    print("  Phase 5 Smoke Test: ALL CHECKS PASSED")
    print("=======================================================")

if __name__ == "__main__":
    main()
