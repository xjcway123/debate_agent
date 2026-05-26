"""裁判 Agent。

两个职责：
1. check_compliance(): 实时合规校验，违规返回 fix_hint 让辩手回退重生成
2. final_scoring(): 终局评分
"""
from __future__ import annotations
import json
import re

from ..core.state import DebateState, Side, Utterance, PhaseKind
from ..core.phases import PhaseSpec
from ..tools.llm import chat
from ..prompts.judge_prompts import (
    COMPLIANCE_SYSTEM, COMPLIANCE_USER_TEMPLATE,
    SCORING_SYSTEM, SCORING_USER_TEMPLATE,
)


def _hard_rules_for(phase: PhaseSpec) -> list[str]:
    rules = [f"字数不得超过约 {phase.max_chars} 字 (容忍 20% 偏差)。"]
    if not phase.can_introduce_new_evidence:
        rules.append("严禁引入此前未出现过的新论据、新论点、新数据。")
    if phase.must_address_opponent:
        rules.append("反驳/质询的对象必须是对方实际说过的内容，不得稻草人。")
    if phase.kind in (PhaseKind.AFF_CROSSEX, PhaseKind.NEG_CROSSEX):
        rules.append("质询必须是问题形式，不得长篇陈述。")
    if phase.kind == PhaseKind.FREE_DEBATE:
        rules.append("单次发言不得过长（200 字以内最佳）。")
    return rules


def _opponent_actual_args(state: DebateState, current_side: Side) -> str:
    """从 trace 中抽出对方实际说过的内容，供稻草人检测。"""
    opp_side: Side = "neg" if current_side == "aff" else "aff"
    lines = []
    for u in state.shared_trace:
        if u.side == opp_side:
            lines.append(f"- [{u.phase.value}] {u.content[:200]}")
    return "\n".join(lines) or "(对方尚未发言)"


class JudgeAgent:
    def __init__(self, state: DebateState):
        self.state = state

    def check_compliance(
        self, phase: PhaseSpec, side: Side, utterance: str
    ) -> tuple[bool, list[str], str]:
        """返回 (是否通过, 违规列表, 修改建议)。"""
        dossier = self.state.dossier(side)
        own_defs = "\n".join(f"- {k}: {v}" for k, v in dossier.definitions.items()) \
                   or "(尚未立论，跳过定义检查)"
        user = COMPLIANCE_USER_TEMPLATE.format(
            motion=self.state.motion,
            phase_name=phase.speaker_role,
            hard_rules="\n".join(f"• {r}" for r in _hard_rules_for(phase)),
            own_definitions=own_defs,
            opponent_actual_args=_opponent_actual_args(self.state, side),
            utterance=utterance,
        )
        raw = chat(COMPLIANCE_SYSTEM, user, model="deepseek-chat",
                   temperature=0.0, max_tokens=400)
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return True, [], ""   # 解析失败时放行，避免阻塞
        try:
            data = json.loads(m.group(0))
            return (
                bool(data.get("passed", True)),
                list(data.get("violations", [])),
                str(data.get("fix_hint", "")),
            )
        except json.JSONDecodeError:
            return True, [], ""

    def final_scoring(self) -> dict:
        user = SCORING_USER_TEMPLATE.format(
            motion=self.state.motion,
            full_transcript=self.state.public_transcript(),
        )
        raw = chat(SCORING_SYSTEM, user, model="deepseek-chat",
                   temperature=0.2, max_tokens=2000)
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return {"error": "评分解析失败", "raw": raw}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as e:
            return {"error": str(e), "raw": raw}
