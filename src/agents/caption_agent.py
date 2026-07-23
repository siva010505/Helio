"""
Caption Agent

Role:
Uses faster-whisper locally to transcribe the voice audio and generate word-level timings.

Inputs:
- voice.wav path

Outputs:
- List of words with start and end timestamps.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class CaptionAgent:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
    def generate_captions(self, voice_path: str) -> List[Dict[str, Any]]:
        """
        Transcribe audio and return word-level timestamps using faster-whisper.
        """
        logger.info("[CaptionAgent] Generating word-level captions using faster-whisper...")
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.error("faster-whisper is not installed. Please pip install faster-whisper.")
            raise
            
        # Initialize the model (using tiny.en for extreme speed since Piper audio is very clean)
        # It downloads to ~/.cache/huggingface if not present
        try:
            # We default to CPU, INT8 for maximum compatibility on Windows without special setup
            video_config = self.config.get("video", {})
            model_size = video_config.get("caption_model", "tiny.en")
            device = video_config.get("caption_device", "cpu")
            model = WhisperModel(model_size, device=device, compute_type="int8")
            
            segments, info = model.transcribe(voice_path, word_timestamps=True)
            
            words = []
            for segment in segments:
                for word in segment.words:
                    words.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end
                    })
                    
            logger.info("[CaptionAgent] Extracted %d words with timings.", len(words))
            return words
        except Exception as exc:
            logger.error("[CaptionAgent] Failed to generate captions: %s", exc)
            raise
