"""
Assembly Agent

Role:
Takes the voice track, the stock videos/images, and the Whisper word-level timestamps,
and combines them using moviepy into a final 1080x1920 vertical video.
It dynamically overlays captions with custom styling and adds Ken Burns to images.
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
        
        self.resolution = tuple(map(int, self.config.get("video", {}).get("resolution", "1080x1920").split('x')))
        
        brand_config = self.config.get("channels", [{}])[0].get("brand", {})
        self.font = brand_config.get("font", os.path.join(os.getcwd(), "assets", "fonts", "Roboto-Bold.ttf"))
        if not os.path.exists(self.font):
            logger.warning("Font %s not found. Captions may fail to render.", self.font)
            self.font = os.path.join(os.getcwd(), "assets", "fonts", "Roboto-Bold.ttf")
            
        self.accent_color = brand_config.get("accent_color", "yellow")
        
        # Priority 1: Separate intro_sting_path and bgm_path
        self.intro_sting_path = brand_config.get("intro_sting_path", "")
        self.bgm_path = brand_config.get("bgm_path", "")
        
        self.logo_path = brand_config.get("logo_path", "assets/logo/channel_logo.png")
        self.watermark_opacity = float(brand_config.get("watermark_opacity", 0.65))

    def _resize_and_crop(self, clip, target_resolution):
        from moviepy.video.fx.Crop import Crop
        from moviepy.video.fx.Resize import Resize
        
        target_w, target_h = target_resolution
        target_ratio = target_w / target_h
        
        clip_w, clip_h = clip.size
        clip_ratio = clip_w / clip_h
        
        if clip_ratio > target_ratio:
            resized_clip = clip.with_effects([Resize(height=target_h)])
            new_w = resized_clip.size[0]
            x_center = new_w / 2
            cropped = resized_clip.with_effects([Crop(x1=x_center - target_w/2, y1=0, x2=x_center + target_w/2, y2=target_h)])
        else:
            resized_clip = clip.with_effects([Resize(width=target_w)])
            new_h = resized_clip.size[1]
            y_center = new_h / 2
            cropped = resized_clip.with_effects([Crop(x1=0, y1=y_center - target_h/2, x2=target_w, y2=y_center + target_h/2)])
            
        return cropped

    def _apply_ken_burns(self, clip, duration, secondary_flashes=None):
        import random
        from moviepy.video.fx.Resize import Resize
        
        ken_burns_cfg = self.config.get("editing", {}).get("ken_burns", {})
        effects = ken_burns_cfg.get("effects", ["zoom_in"])
        zoom_range = ken_burns_cfg.get("zoom_range", [0.08, 0.15])
        
        effect = random.choice(effects)
        zoom_amount = random.uniform(zoom_range[0], zoom_range[1])
        
        punch_cfg = self.config.get("editing", {}).get("punch", {})
        flash_scale = punch_cfg.get("secondary_zoom_flash_scale", 1.18)
        flash_dur = punch_cfg.get("secondary_zoom_flash_duration_seconds", 0.25)
        
        def get_flash_multiplier(t):
            if not secondary_flashes:
                return 1.0
            mult = 1.0
            for flash_t in secondary_flashes:
                dt = abs(t - flash_t)
                if dt < flash_dur / 2:
                    progress = 1.0 - (dt / (flash_dur / 2))
                    mult = max(mult, 1.0 + (flash_scale - 1.0) * progress)
            return mult

        if effect == "zoom_in":
            def resize_func(t):
                return (1.0 + (zoom_amount * t / duration)) * get_flash_multiplier(t)
        elif effect == "zoom_out":
            def resize_func(t):
                return ((1.0 + zoom_amount) - (zoom_amount * t / duration)) * get_flash_multiplier(t)
        else:
            def resize_func(t):
                return (1.0 + zoom_amount) * get_flash_multiplier(t)
            
        base_clip = self._resize_and_crop(clip, self.resolution)
        zoomed_clip = base_clip.with_effects([Resize(resize_func)])
        
        target_w, target_h = self.resolution
        from moviepy.video.fx.Crop import Crop
        
        def crop_func(gf, t):
            zoomed_frame = gf(t)
            h, w, _ = zoomed_frame.shape
            
            if effect == "pan_left":
                max_x = max(0, w - target_w)
                x1 = int(max_x - (max_x * t / duration))
            elif effect == "pan_right":
                max_x = max(0, w - target_w)
                x1 = int(max_x * t / duration)
            else:
                x1 = int((w - target_w) / 2)
                
            y1 = int((h - target_h) / 2)
            
            x1 = max(0, min(x1, w - target_w))
            y1 = max(0, min(y1, h - target_h))
            
            return zoomed_frame[y1:y1+target_h, x1:x1+target_w]
            
        from moviepy import VideoClip
        ken_burns_clip = VideoClip(lambda t: crop_func(zoomed_clip.get_frame, t), duration=duration)
        return ken_burns_clip

    def _apply_zoom_flashes(self, clip, duration, secondary_flashes):
        if not secondary_flashes:
            return clip
            
        from moviepy.video.fx.Resize import Resize
        from moviepy import VideoClip

        punch_cfg = self.config.get("editing", {}).get("punch", {})
        flash_scale = punch_cfg.get("secondary_zoom_flash_scale", 1.18)
        flash_dur = punch_cfg.get("secondary_zoom_flash_duration_seconds", 0.25)
        
        def get_flash_multiplier(t):
            mult = 1.0
            for flash_t in secondary_flashes:
                dt = abs(t - flash_t)
                if dt < flash_dur / 2:
                    progress = 1.0 - (dt / (flash_dur / 2))
                    mult = max(mult, 1.0 + (flash_scale - 1.0) * progress)
            return mult

        target_w, target_h = self.resolution
        
        def resize_func(t):
            return get_flash_multiplier(t)
            
        zoomed_clip = clip.with_effects([Resize(resize_func)])
        
        def crop_func(gf, t):
            zoomed_frame = gf(t)
            h, w, _ = zoomed_frame.shape
            x1 = int((w - target_w) / 2)
            y1 = int((h - target_h) / 2)
            x1 = max(0, min(x1, w - target_w))
            y1 = max(0, min(y1, h - target_h))
            return zoomed_frame[y1:y1+target_h, x1:x1+target_w]
            
        return VideoClip(lambda t: crop_func(zoomed_clip.get_frame, t), duration=duration)

    def assemble_video(self, final_scenes: List[Dict], words_timing: List[Dict], voice_path: str, video_id: int) -> str:
        from moviepy import VideoFileClip, ImageClip, AudioFileClip, TextClip, CompositeVideoClip, CompositeAudioClip
        from moviepy.video.fx.Loop import Loop
        import subprocess
        from imageio_ffmpeg import get_ffmpeg_exe
        
        logger.info("[AssemblyAgent] Starting chunked video assembly for video %s", video_id)
        
        temp_scene_paths = []
        
        for i, scene in enumerate(final_scenes):
            duration = scene["end_time"] - scene["start_time"]
            if duration <= 0:
                continue
                
            flashes = scene.get("zoom_flash_at", [])
            temp_path = self.cache_dir / f"chunk_{video_id}_{i}.mp4"
                
            try:
                path = scene["video_path"]
                if path.lower().endswith(('.jpg', '.jpeg', '.png')):
                    clip = ImageClip(path).with_duration(duration)
                    clip = self._apply_ken_burns(clip, duration, secondary_flashes=flashes)
                else:
                    clip = VideoFileClip(path, audio=False)
                    clip = self._resize_and_crop(clip, self.resolution)
                    
                    if clip.duration < duration:
                        clip = clip.with_effects([Loop(duration=duration)])
                    else:
                        clip = clip.subclipped(0, duration)
                        
                    clip = self._apply_zoom_flashes(clip, duration, flashes)
                    
                # Export chunk to disk to free memory
                clip.write_videofile(str(temp_path), fps=24, codec="libx264", preset="ultrafast", audio=False, logger=None)
                clip.close()
                temp_scene_paths.append(temp_path)
            except Exception as exc:
                logger.error("Failed to process clip for scene %s: %s", scene.get("scene_number"), exc)
                from moviepy import ColorClip
                fallback = ColorClip(size=self.resolution, color=(0,0,0), duration=duration)
                fallback.write_videofile(str(temp_path), fps=24, codec="libx264", preset="ultrafast", audio=False, logger=None)
                fallback.close()
                temp_scene_paths.append(temp_path)
                
        logger.info("[AssemblyAgent] Concatenating %d chunks via FFmpeg.", len(temp_scene_paths))
        concat_txt_path = self.cache_dir / f"concat_{video_id}.txt"
        with open(concat_txt_path, "w") as f:
            for p in temp_scene_paths:
                f.write(f"file '{p.name}'\n")
                
        merged_bg_path = self.cache_dir / f"merged_bg_{video_id}.mp4"
        
        ffmpeg_cmd = [
            get_ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0",
            "-i", concat_txt_path.name,
            "-c", "copy", merged_bg_path.name
        ]
        
        subprocess.run(ffmpeg_cmd, cwd=str(self.cache_dir), check=True)
        
        # Clean up chunks
        for p in temp_scene_paths:
            try:
                os.remove(p)
            except:
                pass
        try:
            os.remove(concat_txt_path)
        except:
            pass
            
        main_video = VideoFileClip(str(merged_bg_path), audio=False)
        
        logger.info("[AssemblyAgent] Adding voice audio from %s", voice_path)
        voice_clip = AudioFileClip(voice_path)
        
        if main_video.duration > voice_clip.duration:
            main_video = main_video.subclipped(0, voice_clip.duration)
            
        audio_clips = [voice_clip]
        
        if self.intro_sting_path and os.path.exists(self.intro_sting_path):
            try:
                sting_clip = AudioFileClip(self.intro_sting_path)
                audio_clips.append(sting_clip)
            except Exception as exc:
                logger.warning("Failed to load intro sting: %s", exc)

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
        
        logger.info("[AssemblyAgent] Generating Karaoke accumulator captions...")
        caption_clips = []
        
        # 1. Group words into chunks (sentences or max 6 words)
        CHUNK_SIZE = 6
        chunks = []
        current_chunk = []
        for word in words_timing:
            w_text = word["word"].strip()
            if not w_text:
                continue
            word["clean_text"] = w_text
            current_chunk.append(word)
            
            # Break on punctuation or max size
            if len(current_chunk) >= CHUNK_SIZE or w_text.endswith(('.', '!', '?', ',')):
                chunks.append(current_chunk)
                current_chunk = []
        if current_chunk:
            chunks.append(current_chunk)
            
        # Helper to get width of a space for padding between words
        try:
            space_clip = TextClip(text="A", font=self.font, font_size=70)
            space_width = space_clip.size[0] * 0.45
            space_clip.close()
        except:
            space_width = 30
            
        MAX_LINE_WIDTH = 900
        LINE_HEIGHT = 90
        base_y_pos = 1400
        
        for chunk in chunks:
            if not chunk: continue
            
            chunk_end = chunk[-1]["end"]
            
            # Pre-calculate widths
            for w in chunk:
                try:
                    dummy = TextClip(text=w["clean_text"], font=self.font, font_size=70, stroke_width=3)
                    w["width"] = dummy.size[0]
                    dummy.close()
                except:
                    w["width"] = 150
            
            # Word-Wrapping Algorithm
            lines = []
            current_line = []
            current_line_width = 0
            
            for w in chunk:
                if not current_line:
                    current_line.append(w)
                    current_line_width = w["width"]
                else:
                    if current_line_width + space_width + w["width"] <= MAX_LINE_WIDTH:
                        current_line.append(w)
                        current_line_width += space_width + w["width"]
                    else:
                        lines.append({"words": current_line, "width": current_line_width})
                        current_line = [w]
                        current_line_width = w["width"]
            
            if current_line:
                lines.append({"words": current_line, "width": current_line_width})
                
            # Vertical Centering of the block
            total_height = len(lines) * LINE_HEIGHT
            start_y = base_y_pos - (total_height / 2)
            
            for line_idx, line in enumerate(lines):
                line_y = start_y + (line_idx * LINE_HEIGHT)
                # Horizontal Centering of this specific line
                current_x = (self.resolution[0] - line["width"]) / 2
                
                for w in line["words"]:
                    text = w["clean_text"]
                    start_t = w["start"]
                    end_t = w["end"]
                    
                    try:
                        # 1. Active Word (Yellow)
                        active_clip = TextClip(
                            text=text, font=self.font, font_size=70, 
                            color=self.accent_color, stroke_color="black", stroke_width=3
                        )
                        active_clip = active_clip.with_position((current_x, line_y)).with_start(start_t).with_end(end_t)
                        caption_clips.append(active_clip)
                        
                        # 2. Past Word (White)
                        if end_t < chunk_end:
                            past_clip = TextClip(
                                text=text, font=self.font, font_size=70, 
                                color="white", stroke_color="black", stroke_width=3
                            )
                            past_clip = past_clip.with_position((current_x, line_y)).with_start(end_t).with_end(chunk_end)
                            caption_clips.append(past_clip)
                            
                    except Exception as exc:
                        logger.warning("Failed to create caption for word '%s': %s", text, exc)
                        
                    current_x += w["width"] + space_width

        if caption_clips:
            logger.info("[AssemblyAgent] Compositing %d caption clips.", len(caption_clips))
            
        final_clips = [main_video] + caption_clips
        
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                from moviepy import ImageClip
                from moviepy.video.fx.Resize import Resize
                watermark = ImageClip(self.logo_path)
                
                # Resize the watermark so it's a small corner logo (e.g., 150px wide)
                if hasattr(watermark, "with_effects"):
                    watermark = watermark.with_effects([Resize(width=150)])
                elif hasattr(watermark, "resize"):
                    watermark = watermark.resize(width=150)
                
                if hasattr(watermark, "with_opacity"):
                    watermark = watermark.with_opacity(self.watermark_opacity)
                elif hasattr(watermark, "set_opacity"):
                    watermark = watermark.set_opacity(self.watermark_opacity)
                    
                if hasattr(watermark, "with_position"):
                    watermark = watermark.with_position((40, 40)).with_duration(main_video.duration)
                else:
                    watermark = watermark.set_position((40, 40)).set_duration(main_video.duration)
                
                final_clips.append(watermark)
                logger.info("[AssemblyAgent] Added watermark from %s", self.logo_path)
            except Exception as e:
                logger.warning("Failed to add watermark: %s", e)

        main_video = CompositeVideoClip(final_clips)
            
        # --- Thumbnail Baking for YouTube Shorts ---
        # YouTube API ignores custom thumbnails for Shorts and often shows a blank grey screen if we try.
        # Workaround: Bake the thumbnail as the very first 0.05 seconds of the video.
        thumbnail_path = f"data/cache/thumbnail_{video_id}.jpg"
        from moviepy import ImageClip, concatenate_videoclips
        
        if os.path.exists(thumbnail_path):
            logger.info("[AssemblyAgent] Baking thumbnail into first frame from %s", thumbnail_path)
            thumb_clip = ImageClip(thumbnail_path).with_duration(0.05)
            # Ensure thumbnail matches the video size
            thumb_clip = thumb_clip.resize(newsize=main_video.size)
            
            # Prepend the thumbnail clip to the main composite video
            main_video = concatenate_videoclips([thumb_clip, main_video], method="compose")
        # -------------------------------------------

        output_path = self.cache_dir / f"final_video_{video_id}.mp4"
        logger.info("[AssemblyAgent] Exporting final video to %s", output_path)
        
        try:
            main_video.write_videofile(
                str(output_path),
                fps=24,
                codec="libx264",
                audio_codec="aac",
                preset="ultrafast",
                threads=4,
                logger=None
            )
            logger.info("[AssemblyAgent] Export successful!")
        except Exception as exc:
            logger.error("[AssemblyAgent] Export failed: %s", exc)
            raise
        finally:
            main_video.close()
            voice_clip.close()
            # Explicitly close TextClips to prevent memory leaks
            for clip in caption_clips:
                clip.close()
            
        return str(output_path)
