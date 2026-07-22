"""
Visual Planner Agent

Role:
Breaks down the generated script into a list of scenes/shots.
Estimates the duration of each scene, and provides a search query and description for the Visual Director.

Inputs:
- final script text

Outputs:
- JSON list of scenes (scene_number, text_segment, search_query, description)
"""

import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

VISUAL_PLANNER_PROMPT = """\
You are an expert video director for YouTube Shorts. Your job is to break down the provided script into 3 to 6 distinct visual scenes.

For each scene, provide:
- "scene_number": The sequential number (1, 2, 3...)
- "text_segment": The exact sentence(s) from the script covered in this scene. Every word of the script must be included exactly once across all scenes.
- "search_query": A short 2-4 word query to search stock video sites (e.g. Pexels/Pixabay) that perfectly matches the text. (e.g., "hacker typing", "robot factory", "abstract data"). Do NOT use abstract words like "concept" or "AI", use literal visual descriptions.
- "description": A brief description of what the visual should convey, to be used to score the footage relevance later.

The output MUST be a JSON list of objects:
[
  {
    "scene_number": 1,
    "text_segment": "Imagine coding without actually coding!",
    "search_query": "typing fast computer",
    "description": "Person typing rapidly on a keyboard, illuminated by screen light."
  },
  ...
]
"""

class VisualPlannerAgent:
    def __init__(self, llm_client):
        self.llm_client = llm_client

    def plan_visuals(self, script_text: str) -> List[Dict[str, Any]]:
        """
        Generate a shot list for the given script.
        """
        logger.info("[VisualPlannerAgent] Planning visuals for script...")
        
        user_prompt = f"Break down this script into scenes:\n\n{script_text}"
        
        try:
            scenes_json = self.llm_client.generate_json(
                system_prompt=VISUAL_PLANNER_PROMPT,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=1500
            )
            
            # If the LLM returned a dict with a key instead of a list, extract it.
            if isinstance(scenes_json, dict):
                for k, v in scenes_json.items():
                    if isinstance(v, list):
                        scenes_json = v
                        break
            
            if not isinstance(scenes_json, list):
                raise ValueError(f"LLM did not return a list of scenes. Got: {type(scenes_json)}")
                
            logger.info("[VisualPlannerAgent] Successfully planned %d scenes.", len(scenes_json))
            return scenes_json
        except Exception as exc:
            logger.error("[VisualPlannerAgent] Visual planning failed: %s", exc)
            raise
