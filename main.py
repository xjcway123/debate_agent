"""新国辩 Agent 入口。

用法：
    export DEEPSEEK_API_KEY="sk-..."
    python -m debate_agent.main --motion "人工智能的发展利大于弊"
    python -m debate_agent.main --motion "..." --free-rounds 4
"""
from __future__ import annotations
import argparse
import json

from .core.moderator import Moderator
from .agents.judge import JudgeAgent
from .agents.reviewer import ReviewerAgent
from .core.exporter import build_markdown, save_markdown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--motion", required=True, help="辩题")
    ap.add_argument("--free-rounds", type=int, default=3,
                    help="自由辩论每方发言轮数")
    ap.add_argument("--out-dir", default="debates",
                    help="Markdown 保存目录")
    ap.add_argument("--json-output", default=None,
                    help="可选：同时输出 JSON 结果")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    mod = Moderator(
        motion=args.motion,
        free_debate_rounds=args.free_rounds,
        verbose=not args.quiet,
    )
    state = mod.run()

    # 评分
    print("\n" + "="*60 + "\n【裁判评分中...】\n" + "="*60)
    judge = JudgeAgent(state)
    verdict = judge.final_scoring()
    print(json.dumps(verdict, ensure_ascii=False, indent=2))

    # 复盘
    print("\n" + "="*60 + "\n【复盘分析中...】\n" + "="*60)
    reviewer = ReviewerAgent(state)
    review = reviewer.review(verdict_summary=json.dumps(verdict, ensure_ascii=False))
    print(json.dumps(review, ensure_ascii=False, indent=2))

    # 准备保存所需的数据结构
    plans = {
        "aff": {
            "standard": state.aff.standard,
            "definitions": state.aff.definitions,
            "main_arguments": state.aff.main_arguments,
            "evidence_count": len(state.aff.unused_evidence) + len(state.aff.used_evidence_ids),
        },
        "neg": {
            "standard": state.neg.standard,
            "definitions": state.neg.definitions,
            "main_arguments": state.neg.main_arguments,
            "evidence_count": len(state.neg.unused_evidence) + len(state.neg.used_evidence_ids),
        },
    }
    transcript = [
        {
            "phase": u.phase.value,
            "side": u.side,
            "speaker_role": u.speaker_role,
            "content": u.content,
        }
        for u in state.shared_trace
    ]

    # 保存 Markdown（用辩题命名）
    md_text = build_markdown(state.motion, plans, transcript, verdict, review)
    md_path = save_markdown(state.motion, md_text, out_dir=args.out_dir)
    print(f"\n[完成] Markdown 已保存至 {md_path}")

    # 可选：JSON
    if args.json_output:
        result = {
            "motion": state.motion,
            "plans": plans,
            "transcript": transcript,
            "verdict": verdict,
            "review": review,
        }
        with open(args.json_output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[完成] JSON 已写入 {args.json_output}")


if __name__ == "__main__":
    main()
