"""
run_analytics_feedback.py

Standalone script for the Helio Feedback Loop.
Should be run every 24-48 hours (e.g., via Windows Task Scheduler or cron).

What it does:
  1. AnalyticsAgent: Finds uploaded videos that are >= 72 hours old and
     pulls their real YouTube Analytics metrics (Views, CTR, AVD) via the API.
     Videos younger than 72 hours are completely ignored.
  2. EvaluationAgent: Reads all mature metrics from the DB, sends them to the
     LLM for correlation analysis, and writes improved prompt instructions back
     to the prompt_versions table so the next production run benefits.

Usage:
    python scripts/run_analytics_feedback.py [--dry-run] [--analytics-only] [--eval-only]
"""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from src.config_loader import load_config
from src.db.db import SessionLocal
from src.db.init_db import init_db
from src.llm_client import LLMClient
from src.agents.analytics_agent import AnalyticsAgent, MATURITY_HOURS
from src.agents.evaluation_agent import EvaluationAgent


def setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/helio_feedback.log", encoding="utf-8"),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Helio Analytics & Feedback Loop Runner.")
    parser.add_argument(
        "--analytics-only",
        action="store_true",
        help="Only pull analytics. Skip evaluation / self-correction.",
    )
    parser.add_argument(
        "--eval-only",
        action="store_true",
        help="Only run evaluation (assumes metrics already in DB). Skip analytics pull.",
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("helio.feedback")

    logger.info("=" * 60)
    logger.info("Helio — Analytics & Feedback Loop Starting")
    logger.info("72-hour video maturity gate is ACTIVE.")
    logger.info("=" * 60)

    init_db()
    config = load_config()

    llm_cfg = config.get("llm", {})
    llm = LLMClient(
        model=llm_cfg.get("model", "meta/llama-3.1-70b-instruct"),
        vision_model=llm_cfg.get("vision_model", "meta/llama-3.2-11b-vision-instruct"),
        temperature=llm_cfg.get("temperature", 0.8),
    )

    db = SessionLocal()
    try:
        # ── Step 1: Pull analytics for mature videos ──────────────────
        if not args.eval_only:
            logger.info(
                "── Step 1: Pulling analytics (videos >= %d h old) ──", MATURITY_HOURS
            )
            analytics = AnalyticsAgent(config, db)
            results = analytics.pull_metrics()
            logger.info("── Analytics Pull Complete. Processed %d videos. ──", len(results))
        else:
            logger.info("── Step 1: Skipped (--eval-only flag). ──")

        # ── Step 2: LLM Evaluation + Self-Correction ──────────────────
        if not args.analytics_only:
            logger.info("── Step 2: Running LLM Evaluation & Self-Correction ──")
            evaluator = EvaluationAgent(llm, db, config)
            result = evaluator.run_evaluation()

            if result.get("status") == "success":
                summary = result["analysis"].get("summary", "N/A")
                logger.info("── Evaluation Complete. Summary: %s ──", summary)
            elif result.get("status") == "skipped":
                logger.info("── Evaluation skipped: %s ──", result.get("reason"))
            else:
                logger.error("── Evaluation failed: %s ──", result.get("error"))
        else:
            logger.info("── Step 2: Skipped (--analytics-only flag). ──")

    finally:
        db.close()

    logger.info("=" * 60)
    logger.info("Helio — Feedback Loop Complete.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
