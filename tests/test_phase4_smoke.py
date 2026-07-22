"""
Phase 4 Smoke Test.
Tests VisualPlannerAgent, CaptionAgent, and VisualDirectorAgent.
Uses a mock short script to test the end-to-end flow.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import json
from dotenv import load_dotenv
load_dotenv()

from src.config_loader import load_config
from src.llm_client import LLMClient
from src.agents.visual_planner_agent import VisualPlannerAgent
from src.agents.caption_agent import CaptionAgent
from src.agents.visual_director_agent import VisualDirectorAgent
from src.agents.voice_agent import VoiceAgent

def main():
    config = load_config()
    llm = LLMClient(
        model=config["llm"]["model"],
        vision_model=config["llm"]["vision_model"],
        temperature=config["llm"]["temperature"]
    )
    ch_cfg = config["channels"][0]

    # Use a very short script to speed up Pexels fetching and Whisper
    script_text = "AI is taking over the world. Robots are building robots. The future is now."
    print("\n--- SCRIPT ---")
    print(script_text)

    print("\n[TEST] 1. Generating Voice (Dependency)...")
    voice_agent = VoiceAgent(ch_cfg)
    audio_path = voice_agent.generate_voice(script_text, ch_cfg.get("voice"), 9999)
    print(f"Voice saved to {audio_path}")

    print("\n[TEST] 2. Planning Visuals...")
    planner = VisualPlannerAgent(llm)
    scenes = planner.plan_visuals(script_text)
    print(f"Planned {len(scenes)} scenes:")
    for s in scenes:
        print(f"  Scene {s['scene_number']}: {s['search_query']} -> {s['description']}")

    print("\n[TEST] 3. Generating Captions (Faster Whisper)...")
    caption_agent = CaptionAgent(ch_cfg)
    words = caption_agent.generate_captions(audio_path)
    print(f"Extracted {len(words)} words. Example: {words[:3]}")

    print("\n[TEST] 4. Directing Visuals (Pexels + Vision LLM)...")
    director = VisualDirectorAgent(llm, config)
    final_scenes = director.select_visuals(scenes, words)
    
    print("\n--- FINAL SCENES ---")
    for s in final_scenes:
        print(f"Scene {s['scene_number']} ({s['start_time']:.2f}s - {s['end_time']:.2f}s): {s['video_path']}")
        assert os.path.exists(s['video_path']) or s['video_path'] == "assets/fallback_visual.mp4", "Video path doesn't exist!"

    print("\n=======================================================")
    print("  Phase 4 Smoke Test: ALL CHECKS PASSED")
    print("=======================================================")

if __name__ == "__main__":
    main()
