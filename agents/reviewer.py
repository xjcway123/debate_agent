"""复盘 Agent。在评分完成后产出战术分析。"""
from __future__ import annotations
import json
import re

from ..core.state import DebateState
from ..tools.llm import chat
from ..prompts.reviewer_prompts import REVIEW_SYSTEM, REVIEW_USER_TEMPLATE


class ReviewerAgent:
    def __init__(self, state: DebateState):
        self.state = state

    def review(self, verdict_summary: str) -> dict:
        user = REVIEW_USER_TEMPLATE.format(
            motion=self.state.motion,
            verdict_summary=verdict_summary,
            full_transcript=self.state.public_transcript(),
        )
        raw = chat(REVIEW_SYSTEM, user, temperature=0.5, max_tokens=2000)
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return {"error": "复盘解析失败", "raw": raw}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as e:
            return {"error": str(e), "raw": raw}
