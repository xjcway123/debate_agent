"""新国辩流程状态机。每个 Phase 自带规则约束，由裁判强制执行。

规则约束分两类：
- 软约束 (soft): 由 prompt 引导
- 硬约束 (hard): 裁判校验，违反则回退重生成
"""
from __future__ import annotations
from dataclasses import dataclass
from .state import PhaseKind, Side


@dataclass
class PhaseSpec:
    kind: PhaseKind
    speaker_side: Side | None       # None 表示双方交替 (自由辩论)
    speaker_role: str               # 显示名
    max_chars: int                  # 字数上限 (近似时间限制)
    can_search: bool                # 本环节是否允许调用检索工具
    can_introduce_new_evidence: bool  # 是否允许首次引入新证据
    must_address_opponent: bool     # 必须针对对方论点 (驳论/质询)
    rules: list[str]                # 给辩手的规则提示 (prompt 用)


# 标准新国辩流程（单人简化版，便于 Agent 实现）
PHASE_FLOW: list[PhaseSpec] = [
    PhaseSpec(
        kind=PhaseKind.AFF_CONSTRUCTIVE,
        speaker_side="aff",
        speaker_role="正方一辩",
        max_chars=900,
        can_search=True,
        can_introduce_new_evidence=True,
        must_address_opponent=False,
        rules=[
            "必须开宗明义：明确辩题、给出关键概念的定义、提出判准 (评判标准)。",
            "提出 2-3 个核心论点，每个论点要有论据支撑。",
            "不要预判对方观点并反驳——你是先手，反方还没说话。",
            "结构建议：定义 → 判准 → 论点一 (论据) → 论点二 (论据) → 小结。",
        ],
    ),
    PhaseSpec(
        kind=PhaseKind.NEG_CONSTRUCTIVE,
        speaker_side="neg",
        speaker_role="反方一辩",
        max_chars=900,
        can_search=True,
        can_introduce_new_evidence=True,
        must_address_opponent=False,
        rules=[
            "若对方定义不当，可重新定义或限定范围，并说明理由。",
            "给出反方判准。可与正方相同，亦可提出更合理的判准。",
            "提出 2-3 个核心论点。可针对正方立论中的明显漏洞，但主要任务是建立反方立场。",
            "结构建议：(澄清定义) → 判准 → 论点一 → 论点二 → 小结。",
        ],
    ),
    PhaseSpec(
        kind=PhaseKind.AFF_CROSSEX,
        speaker_side="aff",
        speaker_role="正方质询",
        max_chars=500,
        can_search=False,
        can_introduce_new_evidence=False,
        must_address_opponent=True,
        rules=[
            "质询是短问短答，不是发表长篇大论。",
            "每个问题要短、要尖、要扣对方逻辑链上的关键节点。",
            "目标：暴露对方定义模糊、论据不实或逻辑跳跃。",
            "输出 2-4 个递进的问题，每问 50 字内。",
            "你是提问方，不需要回答。",
        ],
    ),
    PhaseSpec(
        kind=PhaseKind.NEG_CROSSEX,
        speaker_side="neg",
        speaker_role="反方质询",
        max_chars=500,
        can_search=False,
        can_introduce_new_evidence=False,
        must_address_opponent=True,
        rules=[
            "质询是短问短答，不是发表长篇大论。",
            "每个问题要短、要尖、要扣对方逻辑链上的关键节点。",
            "输出 2-4 个递进的问题，每问 50 字内。",
        ],
    ),
    PhaseSpec(
        kind=PhaseKind.AFF_REBUTTAL,
        speaker_side="aff",
        speaker_role="正方驳论",
        max_chars=700,
        can_search=True,
        can_introduce_new_evidence=True,
        must_address_opponent=True,
        rules=[
            "必须针对反方实际说过的论点反驳，不得稻草人 (扭曲对方观点再打)。",
            "驳论结构：复述对方观点 → 指出问题 (事实/逻辑/价值) → 给出反例或反证。",
            "可顺带强化己方论点，但重心在驳。",
            "不得偷换己方一辩立下的定义。",
        ],
    ),
    PhaseSpec(
        kind=PhaseKind.NEG_REBUTTAL,
        speaker_side="neg",
        speaker_role="反方驳论",
        max_chars=700,
        can_search=True,
        can_introduce_new_evidence=True,
        must_address_opponent=True,
        rules=[
            "必须针对正方实际说过的论点反驳，不得稻草人。",
            "驳论结构：复述对方观点 → 指出问题 → 给出反例或反证。",
            "不得偷换己方一辩立下的定义。",
        ],
    ),
    # 自由辩论：交替发言，由 moderator 在内部循环时切换 side
    PhaseSpec(
        kind=PhaseKind.FREE_DEBATE,
        speaker_side=None,
        speaker_role="自由辩论",
        max_chars=250,           # 单轮发言短
        can_search=False,
        can_introduce_new_evidence=False,
        must_address_opponent=True,
        rules=[
            "短兵相接：每次发言只针对对方上一句话，做出回应、追问、或反驳。",
            "不得长篇大论，单次 200 字内。",
            "不得引入此前未提及的新论据。",
            "可以打断式提问，但要扣紧战场上正在交锋的那个点。",
        ],
    ),
    PhaseSpec(
        kind=PhaseKind.NEG_SUMMARY,
        speaker_side="neg",
        speaker_role="反方四辩",
        max_chars=900,
        can_search=False,
        can_introduce_new_evidence=False,        # 关键：结辩冻结新论据
        must_address_opponent=True,
        rules=[
            "结辩任务：升华价值、总结战场、回应对方核心攻击。",
            "严禁引入此前未出现过的论据或新论点。",
            "梳理 2-3 个胜负手：自己赢在哪 / 对方哪里没回应 / 价值层面谁更深。",
            "结尾要有力，落回辩题。",
        ],
    ),
    PhaseSpec(
        kind=PhaseKind.AFF_SUMMARY,
        speaker_side="aff",
        speaker_role="正方四辩",
        max_chars=900,
        can_search=False,
        can_introduce_new_evidence=False,
        must_address_opponent=True,
        rules=[
            "结辩任务：升华价值、总结战场、回应对方核心攻击。",
            "严禁引入此前未出现过的论据或新论点。",
            "梳理 2-3 个胜负手。",
            "结尾要有力，落回辩题。",
        ],
    ),
]


def phase_by_kind(kind: PhaseKind) -> PhaseSpec:
    for p in PHASE_FLOW:
        if p.kind == kind:
            return p
    raise KeyError(kind)
