"""把辩论结果序列化为 Markdown，供 CLI 和 Streamlit 共用。"""
from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path


def safe_filename(motion: str, max_len: int = 60) -> str:
    """把辩题转成合法文件名，保留中文，剔除路径/控制字符。"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', '', motion).strip()
    cleaned = cleaned.replace(' ', '_')
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned or "未命名辩题"


def build_markdown(
    motion: str,
    plans: dict,
    transcript: list[dict],
    verdict: dict | None,
    review: dict | None,
) -> str:
    """plans: {"aff": {standard, definitions, main_arguments, evidence_count}, "neg": {...}}
       transcript: [{phase, side, speaker_role, content}]
    """
    lines: list[str] = []
    lines.append(f"# {motion}\n")
    lines.append(f"> 新国辩 Agent · 生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 一、作战计划
    lines.append("## 一、赛前作战计划\n")
    for side_key, side_name in [("aff", "正方"), ("neg", "反方")]:
        p = plans.get(side_key, {}) or {}
        lines.append(f"### {side_name}\n")
        lines.append(f"- **判准**：{p.get('standard', '(无)')}")
        defs = p.get("definitions", {}) or {}
        if defs:
            lines.append("- **核心定义**：")
            for k, v in defs.items():
                lines.append(f"  - **{k}**：{v}")
        args = p.get("main_arguments", []) or []
        if args:
            lines.append("- **核心论点**：")
            for a in args:
                lines.append(f"  - {a}")
        lines.append(f"- **检索到证据条数**：{p.get('evidence_count', 0)}\n")

    # 二、实录
    lines.append("## 二、辩论实录\n")
    current_phase = None
    for u in transcript:
        phase = u.get("phase", "")
        if phase != current_phase:
            current_phase = phase
            lines.append(f"\n### 【{phase}】\n")
        side = u.get("side")
        side_tag = "🔵 " if side == "aff" else ("🔴 " if side == "neg" else "")
        lines.append(f"**{side_tag}{u.get('speaker_role','')}**：\n")
        lines.append((u.get("content", "") or "") + "\n")

    # 三、评分
    if verdict and "error" not in verdict:
        lines.append("\n## 三、裁判评分\n")
        winner = verdict.get("winner")
        winner_name = "正方" if winner == "aff" else ("反方" if winner == "neg" else "?")
        conf = verdict.get("confidence", 0) or 0
        lines.append(f"- **胜方**：{winner_name}（置信度 {conf:.0%}）")
        lines.append(f"- **评判理由**：{verdict.get('verdict','')}\n")

        scores = verdict.get("scores", {}) or {}
        aff_s = scores.get("aff", {}) or {}
        neg_s = scores.get("neg", {}) or {}
        all_keys = list(aff_s.keys()) or list(neg_s.keys())
        if all_keys:
            lines.append("### 各维度得分\n")
            lines.append("| 维度 | 正方 | 反方 |")
            lines.append("|------|------|------|")
            for k in all_keys:
                lines.append(f"| {k} | {aff_s.get(k,'-')} | {neg_s.get(k,'-')} |")
            lines.append("")

        clashes = verdict.get("key_clashes", []) or []
        if clashes:
            lines.append("### 战场焦点\n")
            for c in clashes:
                w = c.get("winner", "")
                w_name = {"aff": "正方", "neg": "反方", "tie": "平"}.get(w, w)
                lines.append(f"- **{c.get('issue','')}** → {w_name}：{c.get('reason','')}")
            lines.append("")

    # 四、复盘
    if review and "error" not in review:
        lines.append("\n## 四、复盘建议\n")
        for key, name in [("aff_review", "正方"), ("neg_review", "反方")]:
            r = review.get(key, {}) or {}
            lines.append(f"### {name}\n")
            if r.get("strengths"):
                lines.append("**亮点**")
                for s in r["strengths"]:
                    lines.append(f"- {s}")
            if r.get("missed_opportunities"):
                lines.append("\n**错失机会**")
                for s in r["missed_opportunities"]:
                    lines.append(f"- {s}")
            if r.get("tactical_suggestions"):
                lines.append("\n**改进建议**")
                for s in r["tactical_suggestions"]:
                    lines.append(f"- {s}")
            lines.append("")
        if review.get("best_moment"):
            lines.append(f"\n> ✨ **最精彩瞬间**：{review['best_moment']}")
        if review.get("worst_moment"):
            lines.append(f"\n> 💧 **最低质量瞬间**：{review['worst_moment']}")

    return "\n".join(lines)


def save_markdown(
    motion: str,
    md_text: str,
    out_dir: str | Path = "debates",
) -> Path:
    """保存到 out_dir/<辩题>.md，重名追加时间戳。"""
    save_dir = Path(out_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    name = safe_filename(motion)
    path = save_dir / f"{name}.md"
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = save_dir / f"{name}_{ts}.md"
    path.write_text(md_text, encoding="utf-8")
    return path
