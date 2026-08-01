"""
Research Agent

Role:
Discovers fresh, evergreen narrative-driven topic candidates for the channel's niche via LLM brainstorming.
Deduplicates against the last N topics already used/selected for this channel
before writing candidates to the database.

Inputs:
- channel_config (dict): One channel's config block from config.yaml.
- channel_id (int): DB primary key of the channel row.

Outputs:
- List[dict]: Candidate topic dicts with keys:
    topic_text (str), source (str), description (str)
- Also writes Topic rows (status="candidate") to the DB.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from src.db.models import Topic, Channel

logger = logging.getLogger(__name__)

# Maximum candidates we want to collect before scoring
MAX_CANDIDATES = 15
# Minimum distinct candidates required before handing off to scoring
MIN_CANDIDATES = 3

BRAINSTORM_PROMPT = """\
You are an expert content strategist for a YouTube Shorts channel.
Brainstorm a list of 15 highly engaging, evergreen, narrative-driven topic candidates for the following niche.
Niche: {niche}

Avoid recent news. Focus on psychological, behavioral, historical, or scientific mysteries that tell a compelling story.
Output ONLY a valid JSON object matching this schema:
{{
    "candidates": [
        {{
            "title": "A highly engaging title under 50 characters",
            "description": "A 1-2 sentence description of the narrative arc."
        }}
    ]
}}
"""

SEMANTIC_DEDUP_PROMPT = """\
You are an intelligent semantic filter for a YouTube Shorts channel.
Your job is to read a list of NEW candidate topics and compare them against a list of HISTORICAL topics we have already covered.

You must deeply analyze the underlying meaning, core mystery, and subject matter of each candidate.
Filter out ANY candidate that shares the same core meaning or underlying subject matter as ANY historical topic, even if the title uses completely different words.
Also ensure there are no semantic duplicates within the new candidates themselves.

Historical Topics:
{historical_topics}

New Candidates:
{candidates_json}

Return ONLY a valid JSON object matching this schema containing ONLY the candidates that are completely unique and do not overlap with historical topics:
{{
    "unique_candidates": [
        {{
            "title": "A highly engaging title under 50 characters",
            "description": "A 1-2 sentence description of the narrative arc."
        }}
    ]
}}
"""



class ResearchAgent:
    """
    Discovers and persists candidate topics for a channel.

    Usage:
        agent = ResearchAgent(db_session, llm_client)
        candidates = agent.fetch_candidate_topics(channel_config, channel_id)
    """

    def __init__(self, db_session, llm_client):
        self.db = db_session
        self.llm = llm_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_candidate_topics(
        self,
        channel_config: dict,
        channel_id: int,
    ) -> list[dict]:
        """
        Fetch, deduplicate, and persist candidate topics for a channel.

        Args:
            channel_config: Channel config block from config.yaml.
            channel_id: DB PK of the channel.

        Returns:
            List of persisted candidate topic dicts (topic_text, source, description, db_id).
        """
        niche = channel_config.get("niche", "")
        logger.info("[ResearchAgent] Brainstorming niche: %s", niche)

        # ── 1. Load historical topics for dedup ───────────────────────────
        existing_topics: list[str] = [
            row.topic_text
            for row in self.db.query(Topic)
            .filter(
                Topic.channel_id == channel_id,
                Topic.status.in_(["selected", "used"]),
            )
            .order_by(Topic.created_at.desc())
            .limit(2500)
            .all()
        ]
        logger.info(
            "[ResearchAgent] Found %d recent used/selected topics to avoid.",
            len(existing_topics),
        )

        # ── 1.5. Check latest long-form video for promotion ───────────
        promo_candidate = None
        try:
            import json
            if os.path.exists("latest_long_form.json"):
                with open("latest_long_form.json", "r") as f:
                    lf_data = json.load(f)
                    lf_title = lf_data.get("title")
                    lf_link = lf_data.get("link")
                    if lf_title and lf_link:
                        logger.info("[ResearchAgent] Found latest_long_form.json. Checking semantic duplication for promo: '%s'", lf_title)
                        if not existing_topics:
                            promo_candidate = {"title": lf_title, "description": f"Promo link: {lf_link}", "source": "long_form_promo"}
                        else:
                            historical_str = "\n".join(f"- {t}" for t in existing_topics)
                            sys_prompt = (
                                "You are a semantic deduplicator. Compare the given 'New Title' against the list of 'Historical Topics'. "
                                "If the New Title shares the same core meaning or underlying subject matter as ANY historical topic, return {\"is_duplicate\": true}. "
                                "Otherwise return {\"is_duplicate\": false}. Respond ONLY with valid JSON."
                            )
                            user_prompt = f"Historical:\n{historical_str}\n\nNew Title: {lf_title}"
                            resp = self.llm.generate_json(system_prompt=sys_prompt, user_prompt=user_prompt, temperature=0.1, max_tokens=100)
                            if not resp.get("is_duplicate", True):
                                promo_candidate = {"title": lf_title, "description": f"Promo link: {lf_link}", "source": "long_form_promo"}
                                logger.info("[ResearchAgent] Long-form promo is unique! Injecting as high-priority candidate.")
                            else:
                                logger.info("[ResearchAgent] Long-form promo is a duplicate. Skipping.")
        except Exception as exc:
            logger.error("[ResearchAgent] Failed to process long-form promo: %s", exc)

        # ── 2. Brainstorm via LLM ─────────────────────────────────────
        try:
            system_prompt = BRAINSTORM_PROMPT.format(niche=niche)
            user_prompt = "Generate the JSON response with 15 candidates now."
            
            response = self.llm.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.8,
                max_tokens=1500
            )
            all_raw = response.get("candidates", [])
            for raw in all_raw:
                raw["source"] = "llm_brainstorm"
        except Exception as exc:
            logger.error("[ResearchAgent] LLM brainstorming failed: %s", exc)
            all_raw = []

        logger.info("[ResearchAgent] Total raw results collected: %d", len(all_raw))

        # ── 3. Semantic Deduplication via LLM ─────────────────────────
        logger.info("[ResearchAgent] Running Semantic AI Matching against %d historical topics...", len(existing_topics))
        try:
            if not existing_topics and not all_raw:
                unique = all_raw
            else:
                import json
                historical_str = "\n".join(f"- {t}" for t in existing_topics) if existing_topics else "None"
                candidates_str = json.dumps(all_raw, indent=2)
                sys_prompt = SEMANTIC_DEDUP_PROMPT.format(
                    historical_topics=historical_str,
                    candidates_json=candidates_str
                )
                
                response = self.llm.generate_json(
                    system_prompt=sys_prompt,
                    user_prompt="Filter out semantic duplicates and return the unique candidates.",
                    temperature=0.1,  # Low temp for analytical matching
                    max_tokens=2000
                )
                unique = response.get("unique_candidates", [])
                for u in unique:
                    u["source"] = "llm_brainstorm"
        except Exception as exc:
            logger.error("[ResearchAgent] Semantic deduplication failed: %s", exc)
            unique = all_raw

        # Final exact match safety net
        seen_titles = set()
        final_unique = []
        for u in unique:
            t = u.get("title", "").strip()
            if t and t not in seen_titles:
                seen_titles.add(t)
                final_unique.append(u)
                
        unique = final_unique[:MAX_CANDIDATES]

        # Inject promo candidate at the very top if it exists
        if promo_candidate:
            unique.insert(0, promo_candidate)
            unique = unique[:MAX_CANDIDATES]

        logger.info("[ResearchAgent] Unique candidates after dedup: %d", len(unique))

        if len(unique) < MIN_CANDIDATES:
            logger.warning(
                "[ResearchAgent] Only %d candidates found (minimum is %d). ",
                len(unique), MIN_CANDIDATES,
            )

        # ── 4. Persist to DB ──────────────────────────────────────────
        persisted: list[dict] = []
        for item in unique:
            topic_row = Topic(
                channel_id=channel_id,
                topic_text=item["title"],
                source=item["source"],
                status="candidate",
            )
            self.db.add(topic_row)
            self.db.flush()  # get PK before commit

            persisted.append(
                {
                    "db_id": topic_row.id,
                    "channel_id": channel_id,
                    "topic_text": item["title"],
                    "description": item.get("description", ""),
                    "url": item.get("url", ""),
                    "source": item["source"],
                }
            )

        self.db.commit()
        logger.info(
            "[ResearchAgent] Persisted %d candidates for channel_id=%d.",
            len(persisted), channel_id,
        )
        return persisted
