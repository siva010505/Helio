"""
Feedback Loop Smoke Test.

Simulates the full feedback loop WITHOUT the YouTube API by:
1. Seeding fake uploaded videos and performance metrics directly into the DB.
2. Testing the 72-hour maturity gate (young video should be skipped).
3. Running the EvaluationAgent against the seeded metrics.
4. Verifying that new PromptVersion rows were written for script_agent, seo_agent, scoring_agent.
5. Verifying that ScriptAgent and SEOAgent pick up the new addendum.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta
from src.config_loader import load_config
from src.db.db import SessionLocal
from src.db.init_db import init_db
from src.db.models import Video, PerformanceMetric, PromptVersion
from src.llm_client import LLMClient
from src.agents.analytics_agent import MATURITY_HOURS
from src.agents.evaluation_agent import EvaluationAgent
from src.agents.script_agent import ScriptAgent
from src.agents.seo_agent import SEOAgent

CHANNEL_ID = 1


def seed_fake_data(db):
    """Insert two mature + one immature video and their metrics."""
    now = datetime.utcnow()

    # ── Video A: 80 hours old → MATURE ───────────────────────────────
    v_a = Video(
        channel_id=CHANNEL_ID,
        topic_id=None,
        title="AI is Changing Everything! 🤖",
        hook_style="bold_claim",
        script_text="AI is changing everything. Here is how.",
        youtube_video_id="FAKE_YT_A",
        upload_time=now - timedelta(hours=80),
        status="uploaded",
    )
    # ── Video B: 96 hours old → MATURE ───────────────────────────────
    v_b = Video(
        channel_id=CHANNEL_ID,
        topic_id=None,
        title="Robots That Build Themselves 😮",
        hook_style="question",
        script_text="What if robots could build other robots?",
        youtube_video_id="FAKE_YT_B",
        upload_time=now - timedelta(hours=96),
        status="uploaded",
    )
    # ── Video C: 10 hours old → IMMATURE (should be skipped) ─────────
    v_c = Video(
        channel_id=CHANNEL_ID,
        topic_id=None,
        title="Breaking: ChatGPT Update",
        hook_style="stat",
        script_text="ChatGPT just got a massive update.",
        youtube_video_id="FAKE_YT_C",
        upload_time=now - timedelta(hours=10),
        status="uploaded",
    )
    # ── Video D: 110 hours old → MATURE ──────────────────────────────
    v_d = Video(
        channel_id=CHANNEL_ID,
        topic_id=None,
        title="5 AI Facts That Will Blow Your Mind 🤯",
        hook_style="stat",
        script_text="Did you know AI can now write code better than most humans?",
        youtube_video_id="FAKE_YT_D",
        upload_time=now - timedelta(hours=110),
        status="uploaded",
    )
    db.add_all([v_a, v_b, v_c, v_d])
    db.commit()

    # ── Metrics for A (high performer) seeded 5 days ago ────────────
    db.add(PerformanceMetric(
        video_id=v_a.id, views=45000, likes=3200, comments=120,
        average_view_duration=38.5, average_view_percentage=72.0, ctr=8.2,
        pulled_at=now - timedelta(days=5),
    ))
    # ── Metrics for B (low performer) seeded 5 days ago ──────────────
    db.add(PerformanceMetric(
        video_id=v_b.id, views=2100, likes=80, comments=5,
        average_view_duration=12.0, average_view_percentage=22.0, ctr=1.8,
        pulled_at=now - timedelta(days=5),
    ))
    # ── Metrics for D (medium performer) seeded 5 days ago ───────────
    db.add(PerformanceMetric(
        video_id=v_d.id, views=18000, likes=950, comments=60,
        average_view_duration=28.0, average_view_percentage=52.0, ctr=4.5,
        pulled_at=now - timedelta(days=5),
    ))
    db.commit()
    return v_a, v_b, v_c, v_d


def cleanup_fake_data(db, videos):
    """Remove seeded fake records after test."""
    for v in videos:
        db.query(PerformanceMetric).filter(PerformanceMetric.video_id == v.id).delete()
        db.delete(v)
    db.commit()


def main():
    config = load_config()
    llm = LLMClient(
        model=config["llm"]["model"],
        vision_model=config["llm"]["vision_model"],
        temperature=config["llm"]["temperature"],
    )
    init_db()
    db = SessionLocal()

    try:
        print("\n[TEST] 1. Seeding fake video data...")
        v_a, v_b, v_c, v_d = seed_fake_data(db)
        print(f"  Video A (80h old,  high perf): id={v_a.id}")
        print(f"  Video B (96h old,  low perf):  id={v_b.id}")
        print(f"  Video D (110h old, med perf):  id={v_d.id}")
        print(f"  Video C (10h old,  immature):  id={v_c.id}  <-- should be skipped")

        print(f"\n[TEST] 2. Verifying 72-hour maturity gate...")
        from src.agents.analytics_agent import AnalyticsAgent
        analytics = AnalyticsAgent(config, db)
        mature = analytics._mature_videos()
        mature_ids = {v.id for v in mature}
        
        assert v_a.id in mature_ids, "FAIL: Video A (80h) should be mature!"
        assert v_b.id in mature_ids, "FAIL: Video B (96h) should be mature!"
        assert v_d.id in mature_ids, "FAIL: Video D (110h) should be mature!"
        assert v_c.id not in mature_ids, "FAIL: Video C (10h) must be EXCLUDED!"
        print(f"  [PASS] Maturity gate correct. {len(mature)} video(s) eligible: {mature_ids}")
        print(f"  [PASS] Video C ({v_c.id}) correctly excluded (only 10h old).")

        print(f"\n[TEST] 3. Running EvaluationAgent (LLM analysis + self-correction)...")
        evaluator = EvaluationAgent(llm, db, config)
        result = evaluator.run_evaluation()
        
        assert result.get("status") == "success", f"FAIL: Evaluation status = {result}"
        print(f"  [PASS] Status: success")
        print(f"  Summary: {result['analysis'].get('summary')}")

        print(f"\n[TEST] 4. Verifying PromptVersion rows were written...")
        for agent_name in ["script_agent", "seo_agent", "scoring_agent"]:
            pv = (
                db.query(PromptVersion)
                .filter(
                    PromptVersion.channel_id == CHANNEL_ID,
                    PromptVersion.agent_name == agent_name,
                )
                .order_by(PromptVersion.created_at.desc())
                .first()
            )
            assert pv is not None, f"FAIL: No PromptVersion found for {agent_name}!"
            assert len(pv.prompt_text) > 10, f"FAIL: PromptVersion for {agent_name} is empty!"
            print(f"  [PASS] {agent_name} → v{pv.version_number}: {pv.prompt_text[:80]}...")

        print(f"\n[TEST] 5. Verifying ScriptAgent picks up the addendum...")
        script_agent = ScriptAgent(llm, db)
        addendum = script_agent._get_performance_addendum(CHANNEL_ID)
        assert len(addendum) > 0, "FAIL: ScriptAgent returned empty addendum!"
        print(f"  [PASS] ScriptAgent addendum: {addendum[:80]}...")

        print(f"\n[TEST] 6. Verifying SEOAgent picks up the addendum...")
        seo_agent = SEOAgent(llm, db)
        seo_addendum = seo_agent._get_performance_addendum(CHANNEL_ID)
        assert len(seo_addendum) > 0, "FAIL: SEOAgent returned empty addendum!"
        print(f"  [PASS] SEOAgent addendum: {seo_addendum[:80]}...")

        print("\n=======================================================")
        print("  Feedback Loop Smoke Test: ALL CHECKS PASSED ✅")
        print("=======================================================")

    finally:
        print("\n[CLEANUP] Removing seeded test data...")
        cleanup_fake_data(db, [v_a, v_b, v_c, v_d])
        db.query(PromptVersion).filter(PromptVersion.channel_id == CHANNEL_ID).delete()
        db.commit()
        db.close()
        print("[CLEANUP] Done.")


if __name__ == "__main__":
    main()
