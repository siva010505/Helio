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

    def assemble_video(self, final_scenes: List[Dict], words_timing: List[Dict], voice_path: str, video_id: int, title: str = None, thumb_bg_path: str = None) -> str:
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
        
        logger.info("[AssemblyAgent] Generating Karaoke accumulator captions using PIL...")
        caption_clips = []
        
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
        from moviepy import ImageClip
        
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
            
        try:
            pil_font = ImageFont.truetype(self.font, 70)
        except:
            pil_font = ImageFont.load_default()
            
        # Helper to get text width in Pillow
        def get_text_width(text, font):
            if hasattr(font, 'getbbox'):
                return font.getbbox(text)[2] - font.getbbox(text)[0]
            elif hasattr(font, 'getlength'):
                return int(font.getlength(text))
            else:
                return font.getsize(text)[0]
                
        space_width = get_text_width(" ", pil_font)
        if space_width < 10:
            space_width = 30
            
        MAX_LINE_WIDTH = 900
        LINE_HEIGHT = 90
        base_y_pos = 1400
        W, H = self.resolution
        
        for chunk in chunks:
            if not chunk: continue
            
            # Pre-calculate widths and lines for the whole chunk
            for w in chunk:
                w["width"] = get_text_width(w["clean_text"], pil_font)
                
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
                
            total_height = len(lines) * LINE_HEIGHT
            start_y = base_y_pos - (total_height / 2)
            
            # Generate a sequence of ImageClips for this chunk
            for i in range(len(chunk)):
                # This frame is active from chunk[i]["start"] to chunk[i+1]["start"] (or end of chunk)
                start_t = chunk[i]["start"]
                if i < len(chunk) - 1:
                    end_t = chunk[i+1]["start"]
                else:
                    end_t = chunk[i]["end"]
                    
                if end_t <= start_t:
                    continue
                    
                # Create transparent PIL Image
                img = Image.new('RGBA', (W, H), (0,0,0,0))
                draw = ImageDraw.Draw(img)
                
                # Draw only the words that have been spoken so far (Accumulator Reveal)
                global_w_idx = 0
                for line_idx, line in enumerate(lines):
                    line_y = start_y + (line_idx * LINE_HEIGHT)
                    current_x = (W - line["width"]) / 2
                    
                    for w in line["words"]:
                        if global_w_idx > i:
                            global_w_idx += 1
                            current_x += w["width"] + space_width
                            continue
                            
                        # Active word is Yellow, previously spoken words are White
                        color = self.accent_color if global_w_idx == i else "white"
                        
                        try:
                            # Pillow >= 10.0 supports stroke
                            draw.text((current_x, line_y), w["clean_text"], font=pil_font, fill=color, stroke_width=4, stroke_fill="black")
                        except TypeError:
                            # Fallback for old Pillow without stroke support
                            stroke_width = 4
                            for dx in [-stroke_width, 0, stroke_width]:
                                for dy in [-stroke_width, 0, stroke_width]:
                                    if dx == 0 and dy == 0: continue
                                    draw.text((current_x + dx, line_y + dy), w["clean_text"], font=pil_font, fill="black")
                            draw.text((current_x, line_y), w["clean_text"], font=pil_font, fill=color)
                            
                        current_x += w["width"] + space_width
                        global_w_idx += 1
                        
                frame_array = np.array(img)
                try:
                    clip = ImageClip(frame_array).with_start(start_t).with_end(end_t)
                    caption_clips.append(clip)
                except Exception as exc:
                    logger.warning("Failed to create ImageClip for word: %s", exc)

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

        raw_main_video = main_video
        main_video = CompositeVideoClip(final_clips)
        
        # --- Custom PIL Thumbnail Baking ---
        from moviepy import ImageClip, concatenate_videoclips
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont, ImageEnhance
        
        logger.info("[AssemblyAgent] Generating cinematic custom thumbnail...")
        W, H = self.resolution
        title_text = title if title else "UNTITLED"
        
        # Split text into Setup (line 1) and Hook (line 2)
        words = title_text.split()
        if len(words) > 1:
            line1_text = " ".join(words[:-1]).lower()
            line2_text = words[-1].upper()
        else:
            line1_text = ""
            line2_text = title_text.upper()
            
        # Load the selected thumbnail background
        img = None
        if thumb_bg_path and os.path.exists(thumb_bg_path):
            try:
                if thumb_bg_path.lower().endswith(('.mp4', '.mov', '.webm')):
                    from moviepy import VideoFileClip
                    # Get a frame at 0.5s or halfway if it's shorter
                    temp_clip = VideoFileClip(thumb_bg_path)
                    t = min(0.5, temp_clip.duration / 2) if temp_clip.duration > 0 else 0
                    frame_array = temp_clip.get_frame(t)
                    temp_clip.close()
                    img = Image.fromarray(frame_array).convert('RGB')
                else:
                    img = Image.open(thumb_bg_path).convert('RGB')
                # Resize and crop to fill W,H
                from moviepy.video.fx.Crop import Crop
                from moviepy.video.fx.Resize import Resize
                # Calculate aspect ratio preserving resize
                img_ratio = img.width / img.height
                target_ratio = W / H
                if img_ratio > target_ratio:
                    new_h = H
                    new_w = int(new_h * img_ratio)
                    img = img.resize((new_w, new_h))
                    left = (new_w - W) / 2
                    img = img.crop((left, 0, left + W, H))
                else:
                    new_w = W
                    new_h = int(new_w / img_ratio)
                    img = img.resize((new_w, new_h))
                    top = (new_h - H) / 2
                    img = img.crop((0, top, W, top + H))
                logger.info("[AssemblyAgent] Loaded LLM-selected thumbnail background: %s", thumb_bg_path)
            except Exception as e:
                logger.warning("[AssemblyAgent] Failed to load thumb_bg_path: %s", e)
                img = None
        
        if img is None:
            try:
                # Fallback to first frame of raw video
                bg_frame = raw_main_video.get_frame(1.0)
                img = Image.fromarray(bg_frame).convert('RGB')
            except Exception as e:
                logger.warning("[AssemblyAgent] Failed to grab background frame, using dark grey: %s", e)
                img = Image.new('RGB', (W, H), (20, 20, 20))
                
        # 1. Darken slightly globally
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(0.9)
        
        # 2. Add minimal Vignette (darken edges slightly)
        try:
            import math
            pixels = img.load()
            center_x, center_y = W / 2, H / 2
            max_dist = math.sqrt(center_x**2 + center_y**2)
            
            for y in range(H):
                for x in range(W):
                    dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
                    # Softer falloff
                    factor = 1.0 - (dist / max_dist) ** 2.0
                    # Minimal vignette: limit darkening to 0.7 (70% brightness at edges)
                    factor = max(0.7, min(1.0, factor)) 
                    
                    r, g, b = pixels[x, y]
                    pixels[x, y] = (int(r * factor), int(g * factor), int(b * factor))
        except Exception as e:
            logger.warning("[AssemblyAgent] Failed to apply vignette, skipping: %s", e)
            
        draw = ImageDraw.Draw(img)
        
        try:
            font1 = ImageFont.truetype(self.font, 110)
            font2 = ImageFont.truetype(self.font, 160)
        except:
            font1 = ImageFont.load_default()
            font2 = ImageFont.load_default()
            
        def get_bbox(text, font):
            if hasattr(draw, 'textbbox'):
                return draw.textbbox((0, 0), text, font=font)
            else:
                try:
                    w, h = font.getsize(text)
                    return (0, 0, w, h)
                except:
                    return (0, 0, 100, 100)
                    
        import textwrap
        wrapped_line1 = textwrap.wrap(line1_text, width=18) if line1_text else []
        
        h1_total = 0
        line1_bboxes = []
        for line in wrapped_line1:
            bbox = get_bbox(line, font1)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            line1_bboxes.append((w, h))
            h1_total += h + 10 # line spacing
            
        bbox2 = get_bbox(line2_text, font2)
        w2, h2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]
        
        spacing = 40
        padding_x = 60
        padding_y = 30
        
        box_w = w2 + padding_x * 2
        box_h = h2 + padding_y * 2
        
        total_h = (h1_total + spacing if wrapped_line1 else 0) + box_h
        start_y = (H - total_h) / 2
        
        if wrapped_line1:
            y1 = start_y
            stroke_w = 6
            for i, line in enumerate(wrapped_line1):
                w, h = line1_bboxes[i]
                x1 = (W - w) / 2
                for dx in [-stroke_w, 0, stroke_w]:
                    for dy in [-stroke_w, 0, stroke_w]:
                        if dx == 0 and dy == 0: continue
                        draw.text((x1+dx, y1+dy), line, font=font1, fill="black")
                draw.text((x1, y1), line, font=font1, fill="white")
                y1 += h + 10
            start_y = y1 - 10 + spacing
            
        x2 = (W - box_w) / 2
        y2 = start_y
        
        shadow_offset = 20
        draw.rectangle([x2 + shadow_offset, y2 + shadow_offset, x2 + box_w + shadow_offset, y2 + box_h + shadow_offset], fill=(0, 0, 0))
        draw.rectangle([x2, y2, x2 + box_w, y2 + box_h], fill=(220, 0, 0))
        
        if hasattr(draw, 'textbbox'):
            center_box_x = x2 + box_w / 2
            center_box_y = y2 + box_h / 2
            draw.text((center_box_x, center_box_y), line2_text, font=font2, fill="white", anchor="mm")
        else:
            draw.text((x2 + padding_x, y2 + padding_y), line2_text, font=font2, fill="white")
            
        thumb_array = np.array(img)
        thumb_clip = ImageClip(thumb_array).with_duration(0.5)
        
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
