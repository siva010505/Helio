"""
run_daily_pipeline.py

Entrypoint for Helio's daily automation run.
Wires together config loading, DB setup, LLM client, and the Orchestrator.

Usage:
    python scripts/run_daily_pipeline.py [--dry-run] [--channel CHANNEL_NAME]
"""

import sys
import os
import argparse
import logging

# Allow imports from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from src.config_loader import load_config
from src.db.db import SessionLocal
from src.db.init_db import init_db
from src.llm_client import LLMClient
from src.agents.orchestrator import OrchestratorAgent


class ColoredFormatter(logging.Formatter):
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    RESET = "\033[0m"

    def format(self, record):
        formatted = super().format(record)
        msg = record.getMessage()
        if record.levelno >= logging.ERROR:
            return f"{self.RED}{formatted}{self.RESET}"
        elif record.levelno == logging.WARNING:
            return f"{self.YELLOW}{formatted}{self.RESET}"
        elif "Video uploaded successfully!" in msg or "Phase 8 (Upload) complete." in msg:
            return f"{self.GREEN}{formatted}{self.RESET}"
        return formatted

def setup_logging(level: str = "INFO") -> None:
    os.makedirs("logs", exist_ok=True)
    
    file_handler = logging.FileHandler(
        os.path.join("logs", "helio.log"),
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Helio daily pipeline.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all stages except the final YouTube upload.",
    )
    parser.add_argument(
        "--channel",
        default=None,
        help="Restrict run to a specific channel name (default: all).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    args = parser.parse_args()

    os.makedirs("logs", exist_ok=True)
    setup_logging(args.log_level)
    logger = logging.getLogger("helio.runner")

    logger.info("=" * 60)
    logger.info("Helio — Daily Pipeline Starting (dry_run=%s)", args.dry_run)
    logger.info("=" * 60)

    # ── Initialise DB (idempotent) ────────────────────────────────────
    init_db()

    # ── Load config ───────────────────────────────────────────────────
    config = load_config()

    # ── Filter channels if --channel flag passed ──────────────────────
    if args.channel:
        config["channels"] = [
            ch for ch in config.get("channels", [])
            if ch["name"] == args.channel
        ]
        if not config["channels"]:
            logger.error("Channel '%s' not found in config.yaml.", args.channel)
            sys.exit(1)

    # ── Build shared LLM client ───────────────────────────────────────
    llm_cfg = config.get("llm", {})
    llm = LLMClient(
        model=llm_cfg.get("model", "meta/llama-3.1-70b-instruct"),
        vision_model=llm_cfg.get("vision_model", "meta/llama-3.2-11b-vision-instruct"),
        temperature=llm_cfg.get("temperature", 0.8),
    )

    # ── Run Orchestrator ──────────────────────────────────────────────
    db = SessionLocal()
    try:
        orchestrator = OrchestratorAgent(config, db, llm_client=llm)
        summary = orchestrator.run_daily_plan(dry_run=args.dry_run)
        logger.info("Daily plan summary: %s", summary)
    finally:
        db.close()

    logger.info("=" * 60)
    logger.info("Helio — Daily Pipeline Complete.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
