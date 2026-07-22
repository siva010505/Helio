"""
Analyst Agent

Role:
Pulls analytics for previously uploaded videos and updates prompt strategies
to improve future performance.

Inputs:
- Historical video list (from DB)
- YouTube Analytics API

Outputs:
- Populates `performance_metrics` table.
- Generates new `prompt_versions` based on analysis of what worked.
"""

class AnalystAgent:
    def __init__(self, llm_client, config, db_session):
        self.llm_client = llm_client
        self.config = config
        self.db_session = db_session

    def run_analysis(self):
        # TODO: Pull metrics via YouTube Analytics API
        # TODO: Analyze top performers using LLM and propose new prompts
        pass
