"""辩手 Agent。

核心方法：
- prepare(): 立论前做检索准备
- speak(phase): 在指定环节产生发言
- update_dossier_on_opponent(): 听完对方发言后更新弱点档案
"""
from __future__ import annotations

from ..core.state import DebateState, Side, Evidence, Utterance
from ..core.phases import PhaseSpec
from ..tools.llm import chat
from ..tools.search import search_evidence
from ..prompts.debater_prompts import (
    DEBATER_SYSTEM, DEBATER_USER_TEMPLATE,
    DOSSIER_UPDATE_SYSTEM, DOSSIER_UPDATE_USER,
)


SIDE_NAME = {"aff": "正", "neg": "反"}


class DebaterAgent:
    def __init__(self, side: Side, state: DebateState):
        self.side = side
        self.state = state

    # ---------- 准备阶段：检索 + 立场拟定 ----------
    def prepare(self):
        """立论前调用一次：搜索证据，让 LLM 拟定判准与核心论点。"""
        dossier = self.state.dossier(self.side)
        motion = self.state.motion
        side_name = SIDE_NAME[self.side]

        # 1. 检索
        query = f"{motion} {side_name}方 论据 案例"
        evidence = search_evidence(query, side=self.side, n=6)
        dossier.unused_evidence.extend(evidence)

        # 2. 让 LLM 草拟判准 + 论点
        ev_text = "\n".join(
            f"- [{e.id}] {e.claim}: {e.snippet[:120]}" for e in evidence
        ) or "(暂无检索结果，请基于常识与价值判断展开)"

        plan_sys = f"你是{side_name}方的策略组，请为辩题制定立论框架。"
        plan_user = f"""辩题：{motion}
你的立场：{side_name}方
可用证据：
{ev_text}

请输出 JSON：
{{
  "definitions": {{"关键概念": "你的定义"}},
  "standard": "本方判准 (一句话)",
  "main_arguments": ["论点1 (15字内)", "论点2", "论点3"]
}}"""
        import json, re
        raw = chat(plan_sys, plan_user, temperature=0.4)
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                plan = json.loads(m.group(0))
                dossier.definitions = plan.get("definitions", {})
                dossier.standard = plan.get("standard", "")
                dossier.main_arguments = plan.get("main_arguments", [])
            except json.JSONDecodeError:
                pass

    # ---------- 发言 ----------
    def speak(self, phase: PhaseSpec) -> str:
        """在给定环节生成发言文本（未经裁判校验）。"""
        dossier = self.state.dossier(self.side)
        side_name = SIDE_NAME[self.side]

        # 是否允许引入新证据
        if phase.can_introduce_new_evidence and not self.state.evidence_pool_frozen:
            ev_block = "\n".join(
                f"- [{e.id}] {e.claim}: {e.snippet[:150]}\n  来源: {e.source}"
                for e in dossier.unused_evidence[:8]
            ) or "(无新证据可用)"
            ev_constraint = "本环节允许引入新论据，引用时请用 [证据ID] 标注。"
        else:
            ev_block = "(本环节不得引入新论据，只能基于此前已出现的内容)"
            ev_constraint = "⚠ 本环节严禁引入此前未出现过的新论据或新论点。"

        weaknesses = "\n".join(f"- {w}" for w in dossier.opponent_weaknesses[-5:]) \
                     or "(尚无)"
        main_args = "\n".join(f"- {a}" for a in dossier.main_arguments) or "(尚未拟定)"

        system = DEBATER_SYSTEM.format(side_name=side_name, motion=self.state.motion)
        user = DEBATER_USER_TEMPLATE.format(
            standard=dossier.standard or "(待立论)",
            main_arguments=main_args,
            evidence_block=ev_block,
            opponent_weaknesses=weaknesses,
            transcript=self.state.public_transcript() or "(辩论尚未开始)",
            phase_name=phase.speaker_role,
            phase_rules="\n".join(f"• {r}" for r in phase.rules),
            max_chars=phase.max_chars,
            evidence_constraint=ev_constraint,
        )
        return chat(system, user, temperature=0.75, max_tokens=1500).strip()

    # ---------- 听完对方发言后，更新弱点档案 ----------
    def update_dossier_on_opponent(self, opponent_last: Utterance):
        opp = self.state.opponent(self.side)
        side_name = SIDE_NAME[self.side]
        sys = DOSSIER_UPDATE_SYSTEM.format(side_name=side_name)
        user = DOSSIER_UPDATE_USER.format(
            opponent_last_utterance=opponent_last.content,
            opponent_main_args="\n".join(f"- {a}" for a in opp.main_arguments) or "(未知)",
        )
        result = chat(sys, user, temperature=0.3, max_tokens=400).strip()
        new_weaknesses = [
            line.strip(" -•·\t").strip()
            for line in result.splitlines() if line.strip()
        ]
        dossier = self.state.dossier(self.side)
        dossier.opponent_weaknesses.extend(new_weaknesses[:3])
