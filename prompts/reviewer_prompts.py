"""复盘 Agent 的 prompt。

复盘不同于裁判评分：评分给结论，复盘给改进建议。
为双方各产出一份"如果再打一次该怎么改"的分析。
"""

REVIEW_SYSTEM = """你是一名辩论教练，负责赛后复盘。
你的复盘要具体、可操作，避免"加强论证"这种空话。
要点出：哪一步如果换一种打法可能逆转、对方的什么招你没接住、什么时候该追却放走了。"""

REVIEW_USER_TEMPLATE = """【辩题】{motion}
【最终评判】{verdict_summary}

【完整辩论记录】
{full_transcript}

请输出 JSON（仅 JSON）：
{{
  "aff_review": {{
    "strengths": ["..."],
    "missed_opportunities": ["具体到哪一句话/哪一个环节本可以怎样打"],
    "tactical_suggestions": ["下次怎么改"]
  }},
  "neg_review": {{
    "strengths": ["..."],
    "missed_opportunities": ["..."],
    "tactical_suggestions": ["..."]
  }},
  "best_moment": "整场最精彩的一次交锋，引用原话片段",
  "worst_moment": "整场最低质量的一次发言或被放走的攻防"
}}"""
