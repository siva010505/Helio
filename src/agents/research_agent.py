"""
Research Agent

Role:
Discovers fresh, trending topic candidates for the channel's niche via web search.
Uses Tavily as the primary source and DuckDuckGo as a zero-key fallback.
Deduplicates against the last N topics already used/selected for this channel
before writing candidates to the database.

Inputs:
- channel_config (dict): One channel's config block from config.yaml.
- channel_id (int): DB primary key of the channel row.
- db_session: SQLAlchemy session.

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

# How many days back to look when de-duplicating topics
DEDUP_LOOKBACK_DAYS = 30
# Maximum candidates we want to collect before scoring
MAX_CANDIDATES = 15
# Minimum distinct candidates required before handing off to scoring
MIN_CANDIDATES = 3


def _search_tavily(query: str, niche: str, max_results: int = 10) -> list[dict]:
    """
    Search Tavily for recent news on the given query.

    Returns:
        List of dicts with keys: title, url, content
    """
    try:
        from tavily import TavilyClient
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            logger.warning("TAVILY_API_KEY not set — skipping Tavily search.")
            return []

        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            search_depth="advanced",
            include_answer=False,
            include_raw_content=False,
            max_results=max_results,
            topic="news",
        )
        results = response.get("results", [])
        logger.info("Tavily returned %d results for query: %s", len(results), query)
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("content", "")[:300],
                "source": "tavily",
            }
            for r in results
            if r.get("title")
        ]
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return []


def _search_duckduckgo(query: str, max_results: int = 10) -> list[dict]:
    """
    Search DuckDuckGo News as a free fallback.

    Returns:
        List of dicts with keys: title, url, description, source
    """
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=max_results))

        logger.info("DuckDuckGo returned %d results for query: %s", len(results), query)
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("body", "")[:300],
                "source": "duckduckgo",
            }
            for r in results
            if r.get("title")
        ]
    except Exception as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return []


def _build_search_queries(niche: str) -> list[str]:
    """Generate a small set of diverse search queries for the niche."""
    base = niche.lower().strip()
    today_str = datetime.utcnow().strftime("%B %Y")
    return [
        f"{base} news {today_str}",
        f"latest {base} breakthroughs",
        f"trending {base} topics",
        f"{base} controversy OR announcement",
    ]


def _deduplicate(
    candidates: list[dict],
    existing_topics: list[str],
    seen_titles: set,
) -> list[dict]:
    """
    Remove:
    - Candidates whose title is exactly the same as a previously seen one.
    - Candidates whose title is too similar to a recently-used DB topic.
    - Candidates whose title is too similar to an already-accepted candidate
      in the current batch (cross-batch fuzzy dedup).
    """
    from difflib import SequenceMatcher

    def is_too_similar(a: str, b: str, threshold: float = 0.7) -> bool:
        a_lower = a.lower()
        b_lower = b.lower()
        if a_lower in b_lower or b_lower in a_lower:
            return True
        return SequenceMatcher(None, a_lower, b_lower).ratio() >= threshold

    accepted_titles: list[str] = []  # fuzzy-checked pool of accepted candidates this run
    unique = []

    for c in candidates:
        title = c["title"].strip()
        if not title:
            continue
        # Exact duplicate guard
        if title in seen_titles:
            logger.debug("Filtered (exact dup): %s", title)
            continue
        # Fuzzy check against recent DB topics
        if any(is_too_similar(title, existing) for existing in existing_topics):
            logger.debug("Filtered (too similar to DB history): %s", title)
            continue
        # Fuzzy check against already-accepted candidates in this batch
        if any(is_too_similar(title, accepted) for accepted in accepted_titles):
            logger.debug("Filtered (too similar to accepted candidate): %s", title)
            continue
        seen_titles.add(title)
        accepted_titles.append(title)
        unique.append(c)

    return unique


class ResearchAgent:
    """
    Discovers and persists candidate topics for a channel.

    Usage:
        agent = ResearchAgent(db_session)
        candidates = agent.fetch_candidate_topics(channel_config, channel_id)
    """

    def __init__(self, db_session):
        self.db = db_session

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
        logger.info("[ResearchAgent] Researching niche: %s", niche)

        # ── 1. Load recently-used topics for dedup ────────────────────
        lookback = datetime.utcnow() - timedelta(days=DEDUP_LOOKBACK_DAYS)
        existing_topics: list[str] = [
            row.topic_text
            for row in self.db.query(Topic)
            .filter(
                Topic.channel_id == channel_id,
                Topic.created_at >= lookback,
                Topic.status.in_(["selected", "used"]),
            )
            .all()
        ]
        logger.info(
            "[ResearchAgent] Found %d recent used/selected topics to avoid.",
            len(existing_topics),
        )

        # ── 2. Search ─────────────────────────────────────────────────
        queries = _build_search_queries(niche)
        all_raw: list[dict] = []
        for q in queries:
            results = _search_tavily(q, niche, max_results=8)
            if not results:
                logger.info("Tavily empty for '%s' — falling back to DuckDuckGo.", q)
                results = _search_duckduckgo(q, max_results=8)
            all_raw.extend(results)
            if len(all_raw) >= MAX_CANDIDATES * 2:
                break

        logger.info("[ResearchAgent] Total raw results collected: %d", len(all_raw))

        # ── 3. Deduplicate ────────────────────────────────────────────
        seen_titles: set[str] = set()
        unique = _deduplicate(all_raw, existing_topics, seen_titles)
        unique = unique[:MAX_CANDIDATES]

        logger.info("[ResearchAgent] Unique candidates after dedup: %d", len(unique))

        if len(unique) < MIN_CANDIDATES:
            logger.warning(
                "[ResearchAgent] Only %d candidates found (minimum is %d). "
                "Consider broadening the niche or checking API keys.",
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
