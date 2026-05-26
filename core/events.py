"""辩论事件流。Moderator 通过 yield 这些事件让前端实时观看。

事件类型设计原则：
- 每条事件自包含，前端无需查询额外状态
- 区分"准备/正在生成/已通过裁判/被裁判打回"等中间状态，便于前端展示"裁判介入"亮点
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Any
from .state import Side, PhaseKind


EventKind = Literal[
    "debate_start",          # 辩论开始（含双方判准、论点）
    "phase_start",           # 进入新环节
    "speaking_start",        # 某方开始生成发言
    "speech_done",           # 发言生成完成（待裁判校验）
    "judge_rejected",        # 裁判打回，需重生成
    "speech_committed",      # 发言通过校验，写入 trace
    "phase_end",             # 环节结束
    "verdict",               # 终局评分
    "review",                # 复盘
    "error",                 # 异常
    "finished",              # 全部结束
]


@dataclass
class Event:
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)
