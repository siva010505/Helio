"""
Visual Director Agent

Role:
Retrieves stock footage candidates based on scene queries, extracts a keyframe,
scores them using a Vision LLM, and aligns the final selected videos with precise audio timestamps.

Inputs:
- scenes (from VisualPlannerAgent)
- words (from CaptionAgent)

Outputs:
- Aligned scenes: list of {scene_number, start_time, end_time, video_path, text_segment}
"""

import os
import requests
import base64
import logging
import json
import string
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

# Fallback visual card if no video found
FALLBACK_VISUAL = "assets/fallback_visual.mp4"

def clean_text(text: str) -> str:
    return text.translate(str.maketrans('', '', string.punctuation)).lower().strip()

class VisualDirectorAgent:
    def __init__(self, llm_client, config: Dict[str, Any]):
        self.llm_client = llm_client
        self.config = config
        self.cache_dir = Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.pexels_api_key = os.environ.get("PEXELS_API_KEY")

    def _align_timings(self, scenes: List[Dict], words: List[Dict]) -> List[Dict]:
        """
        Aligns Whisper word timings to the LLM-generated scenes.
        Returns a new list of scenes with 'start_time' and 'end_time'.
        """
        aligned = []
        word_idx = 0
        total_words = len(words)
        
        for i, scene in enumerate(scenes):
            scene_text = clean_text(scene["text_segment"])
            scene_start = words[word_idx]["start"] if word_idx < total_words else 0.0
            
            # Accumulate words until we roughly match the scene text
            accumulated = []
            while word_idx < total_words:
                w_clean = clean_text(words[word_idx]["word"])
                if w_clean:
                    accumulated.append(w_clean)
                word_idx += 1
                
                # Check if we have enough words or reached the end
                # A simple heuristic: if accumulated length is near scene text length
                if len(" ".join(accumulated)) >= len(scene_text) * 0.9:
                    break
                    
            scene_end = words[word_idx - 1]["end"] if word_idx > 0 else 0.0
            
            # Ensure last scene reaches the very end
            if i == len(scenes) - 1 and word_idx < total_words:
                scene_end = words[-1]["end"]
                
            aligned.append({
                **scene,
                "start_time": scene_start,
                "end_time": scene_end
            })
            
        return aligned

    def _search_pexels(self, query: str, limit: int = 3) -> List[str]:
        """Search Pexels for portrait orientation videos and return their download URLs."""
        if not self.pexels_api_key:
            logger.warning("PEXELS_API_KEY missing, skipping Pexels search.")
            return []
            
        url = "https://api.pexels.com/videos/search"
        headers = {"Authorization": self.pexels_api_key}
        params = {"query": query, "per_page": limit, "orientation": "portrait"}
        
        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            videos = []
            for video in data.get("videos", []):
                # Get highest quality portrait video file
                files = video.get("video_files", [])
                if not files: continue
                # Sort by quality/resolution
                files = sorted(files, key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)
                videos.append(files[0]["link"])
            return videos
        except Exception as exc:
            logger.error("Pexels API error: %s", exc)
            return []

    def _extract_frame_base64(self, video_path: str) -> str:
        """Extract a middle frame from a video and convert to base64 jpeg."""
        from moviepy import VideoFileClip
        from PIL import Image
        import io
        
        try:
            clip = VideoFileClip(video_path)
            t = clip.duration / 2.0
            frame = clip.get_frame(t)
            clip.close()
            
            img = Image.fromarray(frame)
            # Resize slightly to save token bandwidth for LLM
            img.thumbnail((512, 512))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=80)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as exc:
            logger.error("Failed to extract frame from %s: %s", video_path, exc)
            return ""

    def _score_video(self, video_path: str, description: str) -> float:
        """Score video relevance using Vision LLM."""
        if not self.config.get("visual_sources", {}).get("vision_scoring", {}).get("enabled", True):
            return 10.0  # Return perfect score if scoring disabled

        b64_image = self._extract_frame_base64(video_path)
        if not b64_image:
            logger.warning("Frame extraction failed for %s, skipping vision score.", video_path)
            return 0.0

        try:
            # description_prompt first, then the base64 image — order matters!
            result = self.llm_client.score_image(description, b64_image)
            score = float(result.get("score", 0.0))
            logger.info("Scored video %s -> %.1f  reason: %s", video_path, score, result.get("reason", ""))
            return score
        except Exception as exc:
            logger.error("Vision scoring failed: %s", exc)
            return 0.0

    def select_visuals(self, scenes: List[Dict], words: List[Dict]) -> List[Dict]:
        """
        Main entrypoint: Align times, fetch footage, score, select best.
        """
        logger.info("[VisualDirector] Aligning timings for %d scenes.", len(scenes))
        aligned_scenes = self._align_timings(scenes, words)
        
        final_scenes = []
        for scene in aligned_scenes:
            logger.info("[VisualDirector] Processing Scene %d: '%s'", scene['scene_number'], scene['search_query'])
            
            urls = self._search_pexels(scene['search_query'])
            best_video_path = None
            best_score = -1.0
            
            # Download and score each candidate
            for idx, url in enumerate(urls):
                cand_path = self.cache_dir / f"cand_s{scene['scene_number']}_{idx}.mp4"
                try:
                    logger.debug("Downloading candidate %s", url)
                    r = requests.get(url, stream=True, timeout=20)
                    r.raise_for_status()
                    with open(cand_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            
                    score = self._score_video(str(cand_path), scene["description"])
                    if score > best_score:
                        best_score = score
                        best_video_path = str(cand_path)
                        
                    # Cleanup non-best to save space?
                    # We will leave cleanup for later or just overwrite
                except Exception as exc:
                    logger.error("Failed handling candidate %d: %s", idx, exc)
                    
            if not best_video_path:
                logger.warning("No valid video found for Scene %d. Using fallback.", scene['scene_number'])
                best_video_path = FALLBACK_VISUAL
                
            final_scenes.append({
                **scene,
                "video_path": best_video_path
            })
            
        return final_scenes
