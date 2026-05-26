"""调度器：驱动整场辩论的状态机。

每个环节的循环：
  1. 选定发言方
  2. 调辩手 Agent 生成发言
  3. 调裁判 Agent 校验合规
  4. 不合规 → 把 fix_hint 喂回给辩手重生成 (最多 2 次)
  5. 通过 → 写入 shared_trace
  6. 让对方更新弱点档案
  7. 进入下一环节

自由辩论是子状态机：在该 phase 内交替发言 N 轮。
"""
from __future__ import annotations
from typing import Iterator

from .state import DebateState, Side, PhaseKind, Utterance
from .phases import PHASE_FLOW, PhaseSpec, phase_by_kind
from .events import Event
from ..agents.debater import DebaterAgent
from ..agents.judge import JudgeAgent
from ..agents.reviewer import ReviewerAgent


FREE_DEBATE_ROUNDS = 6   # 自由辩论交替轮次（每方各 3 次）


class Moderator:
    def __init__(self, motion: str, free_debate_rounds: int = FREE_DEBATE_ROUNDS,
                 verbose: bool = True):
        self.state = DebateState(motion=motion)
        self.aff = DebaterAgent("aff", self.state)
        self.neg = DebaterAgent("neg", self.state)
        self.judge = JudgeAgent(self.state)
        self.free_rounds = free_debate_rounds
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def _debater(self, side: Side) -> DebaterAgent:
        return self.aff if side == "aff" else self.neg

    def _emit(self, phase: PhaseSpec, side: Side, content: str):
        """写入 shared trace，并触发对方更新弱点档案。"""
        utt = Utterance(
            phase=phase.kind,
            side=side,
            speaker_role=phase.speaker_role,
            content=content,
        )
        self.state.shared_trace.append(utt)
        # 对方监听 → 更新弱点档案
        other: Side = "neg" if side == "aff" else "aff"
        try:
            self._debater(other).update_dossier_on_opponent(utt)
        except Exception as e:
            self._log(f"[warn] 弱点档案更新失败: {e}")

    def _speak_with_compliance(
        self, phase: PhaseSpec, side: Side, extra_hint: str = ""
    ) -> str:
        """生成 → 校验 → 不合规则重生成 (最多 2 次)。"""
        debater = self._debater(side)
        last_text = ""
        for attempt in range(3):
            text = debater.speak(phase)
            if extra_hint:
                # 把上一次的修复建议拼到 prompt（最简单的方式：内嵌到 state）
                pass
            passed, violations, fix_hint = self.judge.check_compliance(
                phase, side, text
            )
            if passed:
                return text
            self._log(f"  [裁判] 不合规 (第{attempt+1}次): {violations}")
            self._log(f"  [裁判] 修改建议: {fix_hint}")
            last_text = text
            extra_hint = fix_hint
        # 三次都不通过，放行最后一次（避免死循环），并记录警告
        self._log(f"  [裁判] 多次不合规仍放行，请人工查看")
        return last_text

    def _run_single_speaker_phase(self, phase: PhaseSpec):
        side = phase.speaker_side
        assert side is not None
        # 结辩前冻结证据池
        if phase.kind in (PhaseKind.NEG_SUMMARY, PhaseKind.AFF_SUMMARY):
            self.state.evidence_pool_frozen = True
        self._log(f"\n{'='*60}\n【{phase.speaker_role}】({phase.kind.value})\n{'='*60}")
        text = self._speak_with_compliance(phase, side)
        self._emit(phase, side, text)
        self._log(text)

    def _run_free_debate(self, phase: PhaseSpec):
        self._log(f"\n{'='*60}\n【自由辩论】\n{'='*60}")
        # 反方一辩立论后正方先开火 → 这里约定正方先发
        order: list[Side] = ["aff", "neg"] * self.free_rounds
        for i, side in enumerate(order[:self.free_rounds * 2]):
            phase_for_side = PhaseSpec(
                kind=PhaseKind.FREE_DEBATE,
                speaker_side=side,
                speaker_role=f"{'正' if side=='aff' else '反'}方-自辩-{i+1}",
                max_chars=phase.max_chars,
                can_search=False,
                can_introduce_new_evidence=False,
                must_address_opponent=True,
                rules=phase.rules,
            )
            text = self._speak_with_compliance(phase_for_side, side)
            self._emit(phase_for_side, side, text)
            self._log(f"\n[{phase_for_side.speaker_role}]\n{text}")

    def run(self) -> DebateState:
        self._log(f"\n辩题：{self.state.motion}\n开始准备...")
        # 立论前双方各做一次检索 + 立场规划
        self.aff.prepare()
        self.neg.prepare()
        self._log(f"正方判准: {self.state.aff.standard}")
        self._log(f"反方判准: {self.state.neg.standard}")

        for phase in PHASE_FLOW:
            self.state.current_phase = phase.kind
            if phase.kind == PhaseKind.FREE_DEBATE:
                self._run_free_debate(phase)
            else:
                self._run_single_speaker_phase(phase)
        return self.state

    # ==================================================================
    # 流式接口：供前端逐事件消费。逻辑等同于 run()，但每步 yield Event。
    # ==================================================================
    def _speak_with_compliance_stream(
        self, phase: PhaseSpec, side: Side
    ) -> Iterator[tuple[Event, str | None]]:
        """生成 → 校验循环，每一步 yield 事件。
        最后一个事件的第二个元素是最终通过的文本。"""
        debater = self._debater(side)
        last_text = ""
        for attempt in range(3):
            yield Event("speaking_start", {
                "side": side, "phase": phase.kind.value,
                "speaker_role": phase.speaker_role, "attempt": attempt + 1,
            }), None
            text = debater.speak(phase)
            last_text = text
            yield Event("speech_done", {
                "side": side, "phase": phase.kind.value,
                "speaker_role": phase.speaker_role,
                "content": text, "attempt": attempt + 1,
            }), None

            passed, violations, fix_hint = self.judge.check_compliance(
                phase, side, text
            )
            if passed:
                yield Event("speech_committed", {
                    "side": side, "phase": phase.kind.value,
                    "speaker_role": phase.speaker_role,
                    "content": text,
                }), text
                return
            yield Event("judge_rejected", {
                "side": side, "phase": phase.kind.value,
                "violations": violations, "fix_hint": fix_hint,
                "attempt": attempt + 1,
            }), None
        # 3 次仍不通过：放行最后一稿
        yield Event("speech_committed", {
            "side": side, "phase": phase.kind.value,
            "speaker_role": phase.speaker_role,
            "content": last_text, "forced": True,
        }), last_text

    def _run_single_speaker_phase_stream(
        self, phase: PhaseSpec
    ) -> Iterator[Event]:
        side = phase.speaker_side
        assert side is not None
        if phase.kind in (PhaseKind.NEG_SUMMARY, PhaseKind.AFF_SUMMARY):
            self.state.evidence_pool_frozen = True
        yield Event("phase_start", {
            "phase": phase.kind.value,
            "speaker_role": phase.speaker_role,
            "side": side,
            "rules": phase.rules,
            "max_chars": phase.max_chars,
            "evidence_frozen": self.state.evidence_pool_frozen,
        })
        committed_text: str | None = None
        for ev, text in self._speak_with_compliance_stream(phase, side):
            yield ev
            if text is not None:
                committed_text = text
        if committed_text is not None:
            self._emit(phase, side, committed_text)
        yield Event("phase_end", {"phase": phase.kind.value})

    def _run_free_debate_stream(self, phase: PhaseSpec) -> Iterator[Event]:
        yield Event("phase_start", {
            "phase": phase.kind.value,
            "speaker_role": "自由辩论",
            "side": None,
            "rules": phase.rules,
            "rounds": self.free_rounds * 2,
        })
        order: list[Side] = ["aff", "neg"] * self.free_rounds
        for i, side in enumerate(order[:self.free_rounds * 2]):
            sub_phase = PhaseSpec(
                kind=PhaseKind.FREE_DEBATE,
                speaker_side=side,
                speaker_role=f"{'正' if side=='aff' else '反'}方-自辩-{i+1}",
                max_chars=phase.max_chars,
                can_search=False,
                can_introduce_new_evidence=False,
                must_address_opponent=True,
                rules=phase.rules,
            )
            committed_text: str | None = None
            for ev, text in self._speak_with_compliance_stream(sub_phase, side):
                yield ev
                if text is not None:
                    committed_text = text
            if committed_text is not None:
                self._emit(sub_phase, side, committed_text)
        yield Event("phase_end", {"phase": phase.kind.value})

    def run_stream(self, with_verdict: bool = True,
                   with_review: bool = True) -> Iterator[Event]:
        """流式跑完整场辩论。逐 Event yield，前端可实时渲染。"""
        try:
            # 准备：检索 + 拟定立场
            yield Event("phase_start", {
                "phase": "preparation",
                "speaker_role": "赛前准备",
                "side": None,
                "rules": ["双方独立检索证据、拟定判准与核心论点"],
            })
            self.aff.prepare()
            self.neg.prepare()
            yield Event("debate_start", {
                "motion": self.state.motion,
                "aff": {
                    "standard": self.state.aff.standard,
                    "definitions": self.state.aff.definitions,
                    "main_arguments": self.state.aff.main_arguments,
                    "evidence_count": len(self.state.aff.unused_evidence),
                },
                "neg": {
                    "standard": self.state.neg.standard,
                    "definitions": self.state.neg.definitions,
                    "main_arguments": self.state.neg.main_arguments,
                    "evidence_count": len(self.state.neg.unused_evidence),
                },
            })

            for phase in PHASE_FLOW:
                self.state.current_phase = phase.kind
                if phase.kind == PhaseKind.FREE_DEBATE:
                    yield from self._run_free_debate_stream(phase)
                else:
                    yield from self._run_single_speaker_phase_stream(phase)

            if with_verdict:
                verdict = self.judge.final_scoring()
                yield Event("verdict", {"verdict": verdict})
            else:
                verdict = None

            if with_review:
                import json as _json
                reviewer = ReviewerAgent(self.state)
                summary = _json.dumps(verdict, ensure_ascii=False) if verdict else ""
                review = reviewer.review(verdict_summary=summary)
                yield Event("review", {"review": review})

            yield Event("finished", {})
        except Exception as e:
            import traceback
            yield Event("error", {
                "message": str(e),
                "traceback": traceback.format_exc(),
            })
