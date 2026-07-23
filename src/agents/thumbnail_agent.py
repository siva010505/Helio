"""
Thumbnail Agent

Role:
Extracts a frame from the assembled video and overlays text/graphics
to create a custom thumbnail for YouTube Shorts.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ThumbnailAgent:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.cache_dir = Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        brand_config = self.config.get("channels", [{}])[0].get("brand", {})
        self.font = brand_config.get("font", os.path.join(os.getcwd(), "assets", "fonts", "Roboto-Bold.ttf"))
        self.accent_color = brand_config.get("accent_color", "yellow")
        self.logo_path = brand_config.get("logo_path", "assets/logo/channel_logo.png")

    def generate_thumbnail(self, video_path: str, title: str, video_id: int) -> str:
        """
        Extracts a frame from the middle of the video and adds the title as a thumbnail.
        """
        logger.info("[ThumbnailAgent] Generating thumbnail for video %s", video_id)
        from moviepy import VideoFileClip
        from PIL import Image, ImageDraw, ImageFont
        import textwrap

        output_path = self.cache_dir / f"thumbnail_{video_id}.jpg"

        try:
            # Extract frame at 1/3rd duration (often more interesting than the exact middle)
            clip = VideoFileClip(video_path)
            t = clip.duration / 3.0
            frame = clip.get_frame(t)
            clip.close()

            img = Image.fromarray(frame)
            draw = ImageDraw.Draw(img)

            # Use a fallback font if custom font isn't accessible by PIL directly
            try:
                if not os.path.exists(self.font):
                    logger.warning("Font %s not found. Thumbnail text may fail to render.", self.font)
                font = ImageFont.truetype(self.font, 120)
            except IOError:
                font = ImageFont.load_default()

            # Wrap text and draw
            wrapped_text = textwrap.fill(title, width=20)
            
            # Simple centered text with stroke
            bbox = draw.textbbox((0, 0), wrapped_text, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            W, H = img.size
            x, y = (W - w) / 2, (H - h) / 2

            # Draw stroke/outline
            outline_range = 5
            for dx in range(-outline_range, outline_range+1):
                for dy in range(-outline_range, outline_range+1):
                    draw.text((x+dx, y+dy), wrapped_text, font=font, fill="black", align="center")
            
            # Draw main text
            draw.text((x, y), wrapped_text, font=font, fill=self.accent_color, align="center")

            # Add logo
            if os.path.exists(self.logo_path):
                try:
                    logo = Image.open(self.logo_path).convert("RGBA")
                    # Resize logo
                    logo.thumbnail((200, 200))
                    # Paste at top left with padding
                    img.paste(logo, (50, 50), mask=logo)
                except Exception as e:
                    logger.warning("Failed to overlay logo: %s", e)

            img.save(output_path, "JPEG", quality=90)
            logger.info("[ThumbnailAgent] Thumbnail saved to %s", output_path)
            return str(output_path)

        except Exception as exc:
            logger.error("[ThumbnailAgent] Failed to generate thumbnail: %s", exc)
            return ""
