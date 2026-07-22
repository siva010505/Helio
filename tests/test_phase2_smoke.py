"""
Phase 2 Smoke Test — runs without real API keys.
Tests: config loading, DB session, model imports, ResearchAgent/ScoringAgent instantiation,
dedup logic, score parsing, and orchestrator channel setup.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

# ── 1. Config ──────────────────────────────────────────────────────────
from src.config_loader import load_config
config = load_config()
assert config["channels"][0]["name"] == "ai_news_shorts"
print("[PASS] Config loaded:", config["channels"][0]["name"])

# ── 2. DB init + session ───────────────────────────────────────────────
from src.db.init_db import init_db
from src.db.db import SessionLocal
init_db()
db = SessionLocal()
print("[PASS] DB session created")

# ── 3. Models ──────────────────────────────────────────────────────────
from src.db.models import Channel, Topic, Video, PerformanceMetric, PromptVersion, RunLog
print("[PASS] All models imported")

# ── 4. ResearchAgent instantiation + dedup logic ───────────────────────
from src.agents.research_agent import ResearchAgent, _deduplicate, _build_search_queries
agent_r = ResearchAgent(db)
queries = _build_search_queries("AI News")
assert len(queries) == 4, f"Expected 4 queries, got {len(queries)}"
print("[PASS] ResearchAgent instantiated, queries:", queries)

# Test deduplication
candidates = [
    {"title": "OpenAI releases GPT-5 model today", "source": "tavily", "description": ""},
    {"title": "OpenAI releases GPT-5 model today", "source": "duckduckgo", "description": ""},  # exact dup
    {"title": "OpenAI releases GPT5 model today", "source": "tavily", "description": ""},       # near-exact dup (ratio ~0.93)
    {"title": "Meta unveils Llama 4", "source": "tavily", "description": ""},                   # unique
]
existing = ["GPT-4 Turbo update breaks apps"]
seen = set()
deduped = _deduplicate(candidates, existing, seen)
# Expected: 2 — the exact dup and near-exact dup are filtered, unique title passes through
assert len(deduped) == 2, f"Expected 2 after dedup, got {len(deduped)}: {[d['title'] for d in deduped]}"
print(f"[PASS] Deduplication: {len(candidates)} -> {len(deduped)} candidates")

# ── 5. ScoringAgent instantiation + parse logic ────────────────────────
from src.agents.scoring_agent import ScoringAgent, _parse_scores, _compute_composite, SCORE_WEIGHTS

# Verify weights sum to 1.0
weight_sum = round(sum(SCORE_WEIGHTS.values()), 6)
assert weight_sum == 1.0, f"Score weights don't sum to 1: {weight_sum}"
print(f"[PASS] Score weights sum to 1.0: {SCORE_WEIGHTS}")

# Test composite computation
sample_dims = {"novelty": 8, "virality": 7, "hook_potential": 9, "freshness": 6}
composite = _compute_composite(sample_dims)
expected = 8*0.25 + 7*0.35 + 9*0.25 + 6*0.15
assert abs(composite - expected) < 0.001, f"Composite mismatch: {composite} vs {expected}"
print(f"[PASS] Composite score calculation: {composite:.3f}")

# Test score parsing from mock LLM JSON
mock_candidates = [
    {"db_id": 1, "topic_text": "GPT-5 released", "description": ""},
    {"db_id": 2, "topic_text": "Meta unveils Llama 4", "description": ""},
]
mock_llm_response = [
    {"topic_text": "GPT-5 released", "novelty": 8, "virality": 9, "hook_potential": 9, "freshness": 10, "reasoning": "Breaking news"},
    {"topic_text": "Meta unveils Llama 4", "novelty": 7, "virality": 7, "hook_potential": 8, "freshness": 9, "reasoning": "Hot topic"},
]
parsed = _parse_scores(mock_llm_response, mock_candidates)
assert len(parsed) == 2
assert parsed[0]["composite_score"] > 0
assert all(0 <= v <= 10 for v in parsed[0]["dimensions"].values())
print(f"[PASS] Score parsing: topic='{parsed[0]['topic_text']}' score={parsed[0]['composite_score']}")

# ── 6. ScoringAgent instantiation (no LLM) ────────────────────────────
agent_s = ScoringAgent(llm_client=None, db_session=db)
print("[PASS] ScoringAgent instantiated")

# ── 7. OrchestratorAgent: channel DB setup ─────────────────────────────
from src.agents.orchestrator import OrchestratorAgent
import json
orch = OrchestratorAgent(config, db, llm_client=None)
ch_cfg = config["channels"][0]
channel = orch._ensure_channel_in_db(ch_cfg)
assert channel.id is not None
assert channel.name == "ai_news_shorts"
loaded_cfg = json.loads(channel.config_json)
assert loaded_cfg["niche"] == "AI News"
print(f"[PASS] Channel in DB: id={channel.id}, name={channel.name}")

# Call again → should return existing row (idempotent)
channel2 = orch._ensure_channel_in_db(ch_cfg)
assert channel2.id == channel.id
print(f"[PASS] _ensure_channel_in_db is idempotent")

# ── 8. Cleanup ─────────────────────────────────────────────────────────
db.close()
print()
print("=" * 55)
print("  Phase 2 Smoke Test: ALL CHECKS PASSED")
print("=" * 55)
