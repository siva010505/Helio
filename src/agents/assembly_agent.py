"""
Assembly Agent

Role:
Takes the voice track, the stock videos, and the Whisper word-level timestamps,
and combines them using moviepy into a final 1080x1920 vertical video.
It dynamically overlays captions with custom styling.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class AssemblyAgent:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.cache_dir = Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load configs
        self.resolution = tuple(map(int, self.config.get("video", {}).get("resolution", "1080x1920").split('x')))
        
        brand_config = self.config.get("channels", [{}])[0].get("brand", {})
        self.font = brand_config.get("font", os.path.join(os.getcwd(), "assets", "fonts", "Roboto-Bold.ttf"))
        # Ensure fallback font if custom font not found
        if not os.path.exists(self.font):
            logger.warning("Font %s not found. Captions may fail to render.", self.font)
            self.font = os.path.join(os.getcwd(), "assets", "fonts", "Roboto-Bold.ttf")
            
        self.accent_color = brand_config.get("accent_color", "yellow")
        self.bgm_path = brand_config.get("intro_sting_path", "")

    def _resize_and_crop(self, clip, target_resolution):
        """
        Resizes and crops a VideoFileClip to the target vertical resolution (e.g. 1080x1920)
        by maintaining aspect ratio and center-cropping.
        """
        from moviepy.video.fx.Crop import Crop
        from moviepy.video.fx.Resize import Resize
        
        target_w, target_h = target_resolution
        target_ratio = target_w / target_h
        
        clip_w, clip_h = clip.size
        clip_ratio = clip_w / clip_h
        
        if clip_ratio > target_ratio:
            # Clip is wider than target. Scale based on height.
            resized_clip = clip.with_effects([Resize(height=target_h)])
            # Center crop width
            new_w = resized_clip.size[0]
            x_center = new_w / 2
            cropped = resized_clip.with_effects([Crop(x1=x_center - target_w/2, y1=0, x2=x_center + target_w/2, y2=target_h)])
        else:
            # Clip is taller than target. Scale based on width.
            resized_clip = clip.with_effects([Resize(width=target_w)])
            # Center crop height
            new_h = resized_clip.size[1]
            y_center = new_h / 2
            cropped = resized_clip.with_effects([Crop(x1=0, y1=y_center - target_h/2, x2=target_w, y2=y_center + target_h/2)])
            
        return cropped

    def assemble_video(self, final_scenes: List[Dict], words_timing: List[Dict], voice_path: str, video_id: int) -> str:
        """
        Assembles the final video.
        """
        from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, CompositeAudioClip, concatenate_videoclips
        from moviepy.video.fx.Loop import Loop
        
        logger.info("[AssemblyAgent] Starting video assembly for video %s", video_id)
        
        # 1. Prepare visual scene clips
        scene_clips = []
        for scene in final_scenes:
            duration = scene["end_time"] - scene["start_time"]
            if duration <= 0:
                continue
                
            try:
                # Load clip
                clip = VideoFileClip(scene["video_path"])
                
                # Resize and crop to 9:16
                clip = self._resize_and_crop(clip, self.resolution)
                
                # Adjust duration (loop if too short, trim if too long)
                if clip.duration < duration:
                    clip = clip.with_effects([Loop(duration=duration)])
                else:
                    clip = clip.subclipped(0, duration)
                    
                scene_clips.append(clip)
            except Exception as exc:
                logger.error("Failed to process clip for scene %s: %s", scene.get("scene_number"), exc)
                # Fallback blank clip if fails
                from moviepy import ColorClip
                fallback = ColorClip(size=self.resolution, color=(0,0,0), duration=duration)
                scene_clips.append(fallback)
                
        # 2. Concatenate base visuals
        logger.info("[AssemblyAgent] Concatenating %d scenes.", len(scene_clips))
        main_video = concatenate_videoclips(scene_clips, method="compose")
        
        # 3. Add Voice Audio
        logger.info("[AssemblyAgent] Adding voice audio from %s", voice_path)
        voice_clip = AudioFileClip(voice_path)
        
        # Ensure video duration matches audio duration
        if main_video.duration > voice_clip.duration:
            main_video = main_video.subclipped(0, voice_clip.duration)
            
        # 4. Add Background Music (if available)
        audio_clips = [voice_clip]
        if self.bgm_path and os.path.exists(self.bgm_path):
            try:
                from moviepy.audio.fx.MultiplyVolume import MultiplyVolume
                from moviepy.audio.fx.AudioLoop import AudioLoop
                bgm_clip = AudioFileClip(self.bgm_path)
                bgm_clip = bgm_clip.with_effects([MultiplyVolume(0.1), AudioLoop(duration=main_video.duration)])
                audio_clips.append(bgm_clip)
            except Exception as exc:
                logger.warning("Failed to load BGM: %s", exc)
                
        final_audio = CompositeAudioClip(audio_clips)
        main_video = main_video.with_audio(final_audio)
        
        # 5. Add Captions
        logger.info("[AssemblyAgent] Generating caption overlays...")
        caption_clips = []
        
        # Word by word animation
        for word in words_timing:
            w_text = word["word"].strip()
            if not w_text:
                continue
                
            try:
                # Create text clip with stroke for visibility
                txt_clip = TextClip(
                    text=w_text,
                    font=self.font,
                    font_size=80,
                    color=self.accent_color,
                    stroke_color="black",
                    stroke_width=3,
                    method="caption",
                    size=(self.resolution[0] - 100, 250),
                    text_align="center"
                )
                
                # Position near bottom center
                txt_clip = txt_clip.with_position(("center", 1400))
                # Set timing
                txt_clip = txt_clip.with_start(word["start"]).with_end(word["end"])
                
                caption_clips.append(txt_clip)
            except Exception as exc:
                logger.warning("Failed to create caption for word '%s': %s", w_text, exc)

        if caption_clips:
            logger.info("[AssemblyAgent] Compositing %d caption clips.", len(caption_clips))
            main_video = CompositeVideoClip([main_video] + caption_clips)
            
        # 6. Export
        output_path = self.cache_dir / f"final_video_{video_id}.mp4"
        logger.info("[AssemblyAgent] Exporting final video to %s", output_path)
        
        try:
            main_video.write_videofile(
                str(output_path),
                fps=24,
                codec="libx264",
                audio_codec="aac",
                preset="ultrafast",  # Use faster encoding for tests
                threads=4,
                logger=None # Suppress moviepy progress bar in logs
            )
            logger.info("[AssemblyAgent] Export successful!")
        except Exception as exc:
            logger.error("[AssemblyAgent] Export failed: %s", exc)
            raise
        finally:
            main_video.close()
            voice_clip.close()
            
        return str(output_path)
