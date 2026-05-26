"""辩论状态：共享 trace + 双方私有档案 + 论据池。

设计原则：
- 公开发言进入 shared_trace，所有 Agent 可见
- 私有思考（弱点档案、未出论据、内心 OS）放在 PrivateDossier，仅本方可见
- evidence_pool 在结辩前冻结，结辩阶段不得引入新论据
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


Side = Literal["aff", "neg"]  # 正方 aff / 反方 neg


class PhaseKind(str, Enum):
    AFF_CONSTRUCTIVE = "aff_constructive"   # 正方立论
    NEG_CONSTRUCTIVE = "neg_constructive"   # 反方立论
    AFF_CROSSEX      = "aff_crossex"        # 正方质询反方
    NEG_CROSSEX      = "neg_crossex"        # 反方质询正方
    AFF_REBUTTAL     = "aff_rebuttal"       # 正方驳论
    NEG_REBUTTAL     = "neg_rebuttal"       # 反方驳论
    FREE_DEBATE      = "free_debate"        # 自由辩论
    NEG_SUMMARY      = "neg_summary"        # 反方结辩
    AFF_SUMMARY      = "aff_summary"        # 正方结辩
    REVIEW           = "review"             # 赛后复盘


@dataclass
class Utterance:
    """一次发言（已通过裁判合规校验后才入 trace）。"""
    phase: PhaseKind
    side: Side | None             # 自由辩论之外为单方; 仅复盘为 None
    speaker_role: str             # "正方一辩" / "反方一辩" / "裁判" / "复盘"
    content: str
    citations: list[str] = field(default_factory=list)  # 引用的 evidence id
    token_count: int = 0


@dataclass
class Evidence:
    """一条检索得到的证据（绑定到使用方，结辩前冻结）。"""
    id: str
    side: Side
    claim: str          # 用一句话概括它支持的论点
    snippet: str        # 原文摘录
    source: str         # URL 或来源名


@dataclass
class PrivateDossier:
    """辩手私有档案。对方看不到。"""
    side: Side
    definitions: dict[str, str] = field(default_factory=dict)   # 一辩立论确立的核心概念
    standard: str = ""                                           # 判准
    main_arguments: list[str] = field(default_factory=list)      # 自己的论点
    opponent_weaknesses: list[str] = field(default_factory=list) # 对手弱点档案 (逐轮更新)
    unused_evidence: list[Evidence] = field(default_factory=list)
    used_evidence_ids: set[str] = field(default_factory=set)


@dataclass
class DebateState:
    motion: str                                  # 辩题
    shared_trace: list[Utterance] = field(default_factory=list)
    aff: PrivateDossier = field(default_factory=lambda: PrivateDossier(side="aff"))
    neg: PrivateDossier = field(default_factory=lambda: PrivateDossier(side="neg"))
    evidence_pool_frozen: bool = False           # 进入结辩后置 True
    current_phase: PhaseKind = PhaseKind.AFF_CONSTRUCTIVE

    def dossier(self, side: Side) -> PrivateDossier:
        return self.aff if side == "aff" else self.neg

    def opponent(self, side: Side) -> PrivateDossier:
        return self.neg if side == "aff" else self.aff

    def public_transcript(self) -> str:
        """所有 Agent 可见的公开记录。"""
        lines = []
        for u in self.shared_trace:
            tag = f"[{u.phase.value}|{u.speaker_role}]"
            lines.append(f"{tag} {u.content}")
        return "\n\n".join(lines)
