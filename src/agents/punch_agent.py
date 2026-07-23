"""
Punch Agent

Role:
Detects emphasis moments in the script (numbers/stats and configured trigger
words), matches them to exact timestamps using word-level timing data, and
classifies each as "primary" (gets a dedicated short cutaway clip) or
"secondary" (gets a free zoom-flash effect applied to existing footage).

This is fully heuristic / regex-based — no LLM call is used for detection,
to keep this feature's cost as close to $0 extra as possible.
"""
import re
import string
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

def clean_text(text: str) -> str:
    return text.translate(str.maketrans('', '', string.punctuation)).lower().strip()

class PunchAgent:
    def identify_punch_moments(self, script_text: str, words_timing: List[Dict], channel_config: Dict[str, Any]) -> List[Dict]:
        punch_cfg = channel_config.get("editing", {}).get("punch", {})
        if not punch_cfg.get("enabled", True):
            return []
            
        trigger_words = punch_cfg.get("trigger_words", [])
        max_punches = punch_cfg.get("max_punch_moments", 6)
        primary_count = punch_cfg.get("primary_punch_count", 3)
        
        # Build regex for numbers (digits, percentages, currencies)
        number_pattern = re.compile(r'\b\d+(?:,\d+)*(?:\.\d+)?\b|\b\d+%\b|\$\d+')
        
        candidates = []
        
        # 1. Find all words in words_timing matching trigger words or numbers
        for wt in words_timing:
            raw_word = wt.get("word", "")
            c_word = clean_text(raw_word)
            if not c_word:
                continue
                
            is_number = bool(number_pattern.search(raw_word))
            is_trigger = c_word in trigger_words
            
            if is_number or is_trigger:
                candidates.append({
                    "word": c_word,
                    "timestamp": wt["start"],
                    "is_number": is_number
                })
                
        # Deduplicate by timestamp (avoid multiple hits on same word)
        seen_times = set()
        unique_cands = []
        for c in candidates:
            if c["timestamp"] not in seen_times:
                unique_cands.append(c)
                seen_times.add(c["timestamp"])
                
        # Sort candidates: Priority 1: is_number (True first), Priority 2: earlier timestamp
        unique_cands.sort(key=lambda x: (not x["is_number"], x["timestamp"]))
        
        # Cap to max punches
        final_cands = unique_cands[:max_punches]
        
        # Assign tiers
        for i, cand in enumerate(final_cands):
            cand["tier"] = "primary" if i < primary_count else "secondary"
            logger.info("[PunchAgent] Found %s punch moment at %.2fs: '%s'", cand["tier"], cand["timestamp"], cand["word"])
            
        return final_cands
