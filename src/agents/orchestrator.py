"""
Orchestrator Agent ("Helio")

Role:
The system's CEO agent. On each daily run it:
  1. Reads config for all active channels.
  2. Ensures each channel exists in the DB.
  3. Reads the latest PromptVersion recommendations (from the Analyst Agent)
     so that downstream agents use proven prompts.
  4. Calls the ResearchAgent to discover fresh candidates.
  5. Calls the ScoringAgent to select the best topics.
  6. Calls run_pipeline() once per selected topic (Phase 3+).
  7. Writes a RunLog record summarising the day's activity.

Inputs:
- config (dict): Loaded config.yaml.
- db_session: SQLAlchemy session.
- llm_client (LLMClient): Shared LLM client instance.

Outputs:
- Triggers sub-agents in sequence.
- Writes a daily summary to the `run_logs` database table.
"""

import json
import logging
from datetime import datetime

from src.db.models import Channel, RunLog
from src.agents.research_agent import ResearchAgent
from src.agents.scoring_agent import ScoringAgent

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """
    Coordinates the full daily pipeline across all configured channels.

    Usage:
        orchestrator = OrchestratorAgent(config, db_session, llm_client)
        orchestrator.run_daily_plan(dry_run=False)
    """

    def __init__(self, config: dict, db_session, llm_client=None):
        self.config = config
        self.db = db_session
        self.llm = llm_client  # May be None until Phase 3 for pipeline steps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_daily_plan(self, dry_run: bool = False) -> dict:
        """
        Execute the full daily automation plan.

        Args:
            dry_run: If True, performs all steps except the final upload.

        Returns:
            Summary dict written to RunLog.
        """
        run_log = RunLog(
            run_type="daily_pipeline" if not dry_run else "dry_run",
            started_at=datetime.utcnow(),
            status="running",
            summary_json="{}",
        )
        self.db.add(run_log)
        self.db.commit()

        summary = {"channels": [], "dry_run": dry_run}

        try:
            for ch_cfg in self.config.get("channels", []):
                ch_summary = self._run_channel(ch_cfg, dry_run=dry_run)
                summary["channels"].append(ch_summary)

            run_log.status = "success"
            logger.info("[Orchestrator] Daily plan complete.")

        except Exception as exc:
            logger.error("[Orchestrator] Daily plan failed: %s", exc, exc_info=True)
            run_log.status = "failed"
            run_log.error_text = str(exc)
            raise

        finally:
            run_log.finished_at = datetime.utcnow()
            run_log.summary_json = json.dumps(summary, default=str)
            self.db.commit()

        return summary

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_channel_in_db(self, ch_cfg: dict) -> Channel:
        """Get or create the Channel row for this config block."""
        channel = (
            self.db.query(Channel).filter(Channel.name == ch_cfg["name"]).first()
        )
        if not channel:
            channel = Channel(
                name=ch_cfg["name"],
                niche=ch_cfg.get("niche", ""),
                config_json=json.dumps(ch_cfg),
            )
            self.db.add(channel)
            self.db.commit()
            logger.info("[Orchestrator] Created new channel: %s", ch_cfg["name"])
        else:
            # Keep config_json in sync with config.yaml
            channel.config_json = json.dumps(ch_cfg)
            self.db.commit()
        return channel

    def _run_channel(self, ch_cfg: dict, dry_run: bool) -> dict:
        """Run research → scoring → pipeline for a single channel."""
        channel_name = ch_cfg.get("name", "unknown")
        videos_per_day = ch_cfg.get("videos_per_day", 1)

        logger.info(
            "[Orchestrator] ── Channel: %s ── Target: %d video(s) today",
            channel_name, videos_per_day,
        )

        ch_summary = {
            "channel": channel_name,
            "candidates_found": 0,
            "selected_topics": [],
            "videos_created": [],
            "errors": [],
        }

        # ── Ensure channel exists in DB ───────────────────────────────
        channel = self._ensure_channel_in_db(ch_cfg)

        # ── Phase 2: Research ─────────────────────────────────────────
        research_agent = ResearchAgent(self.db)
        try:
            candidates = research_agent.fetch_candidate_topics(
                channel_config=ch_cfg,
                channel_id=channel.id,
            )
            ch_summary["candidates_found"] = len(candidates)
            logger.info(
                "[Orchestrator] Research complete: %d candidate(s) found.", len(candidates)
            )
        except Exception as exc:
            msg = f"ResearchAgent failed: {exc}"
            logger.error("[Orchestrator] %s", msg, exc_info=True)
            ch_summary["errors"].append(msg)
            return ch_summary

        if not candidates:
            ch_summary["errors"].append("No candidates found — skipping scoring.")
            return ch_summary

        # ── Phase 2: Scoring ──────────────────────────────────────────
        if not self.llm:
            logger.warning(
                "[Orchestrator] LLMClient not provided — cannot score. "
                "Selecting first %d candidates by order.",
                videos_per_day,
            )
            selected = candidates[:videos_per_day]
        else:
            scoring_agent = ScoringAgent(self.llm, self.db)
            try:
                selected = scoring_agent.score_and_select(
                    channel_config=ch_cfg,
                    channel_id=channel.id,
                    candidates=candidates,
                    videos_per_day=videos_per_day,
                )
            except Exception as exc:
                msg = f"ScoringAgent failed: {exc}"
                logger.error("[Orchestrator] %s", msg, exc_info=True)
                ch_summary["errors"].append(msg)
                return ch_summary

        ch_summary["selected_topics"] = [
            {
                "topic_text": s["topic_text"],
                "score": s.get("composite_score", None),
            }
            for s in selected
        ]
        logger.info(
            "[Orchestrator] Scoring complete: %d topic(s) selected.", len(selected)
        )

        # ── Phase 3+: Video Pipeline (stub — implemented in later phases) ─
        for topic in selected:
            try:
                video_result = self._run_video_pipeline(
                    ch_cfg, channel, topic, dry_run=dry_run
                )
                ch_summary["videos_created"].append(video_result)
            except Exception as exc:
                msg = f"Pipeline failed for '{topic['topic_text']}': {exc}"
                logger.error("[Orchestrator] %s", msg, exc_info=True)
                ch_summary["errors"].append(msg)

        return ch_summary

    def _run_video_pipeline(
        self, ch_cfg: dict, channel: Channel, topic: dict, dry_run: bool
    ) -> dict:
        """
        Call the video creation pipeline for a single selected topic.
        Phase 3+ will fill this in. For now, it is a structured stub.
        """
        from src.pipeline import run_pipeline

        logger.info(
            "[Orchestrator] Starting pipeline for topic: %s", topic["topic_text"]
        )
        result = run_pipeline(
            channel_config=ch_cfg,
            topic=topic,
            db_session=self.db,
            llm_client=self.llm,
            dry_run=dry_run,
        )
        return result or {"topic": topic["topic_text"], "status": "stub — not yet implemented"}
