# Helio — Autonomous YouTube Shorts Channel Agent

Helio is a fully autonomous AI system that runs a YouTube Shorts channel end-to-end, with zero recurring monetary cost. 

## Features
- Research trending topics in a defined niche
- Pick the strongest topics and write scripts
- Generate voice narration, visuals, and captions entirely via local/free tools
- Assemble a finished vertical Short (video file)
- Generate SEO metadata (title, description, tags, hashtags)
- Upload automatically via YouTube Data API v3
- Pull performance analytics and adjust strategy autonomously

## Setup
1. Copy `.env.example` to `.env` and fill in API keys.
2. Install dependencies: `pip install -r requirements.txt`
3. Initialize DB: `python src/db/init_db.py`
4. Add assets (`assets/music`, `assets/fonts`, `assets/logo`).
5. Run daily pipeline: `python scripts/run_daily_pipeline.py`
