"""Streamlit 前端：流式观看新国辩 Agent。

启动：
    export DEEPSEEK_API_KEY="sk-..."
    streamlit run debate_agent/app.py

设计要点：
- 左侧：辩题输入 + 双方"作战计划"面板（判准/论点/证据数）
- 中央：辩论实时流。每个环节一个折叠面板，发言按顺序追加。
- 裁判介入 (judge_rejected) 用警示色高亮，展示"违规-修复"全过程，这是亮点。
- 右侧：当前环节规则提示、进度。
- 底部：终局评分 + 复盘，跑完后渲染。
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path

import streamlit as st

# 兼容两种放置方式：
# (A) 项目根/debate_agent/app.py，运行 `streamlit run debate_agent/app.py`
# (B) 用户把 debate_agent/ 直接当工作目录，app.py 就在里面
#     运行 `streamlit run app.py`
_THIS = Path(__file__).resolve()
_PKG_DIR = _THIS.parent              # 包含 core/, agents/ 等
_PARENT = _PKG_DIR.parent            # 包目录的上一层
if (_PKG_DIR / "core").is_dir() and not (_PARENT / "debate_agent").is_dir():
    # (B) app.py 就在 debate_agent/ 内，但上一层没有 debate_agent/ 包
    # → 把上一层临时建成包根：sys.path 加上 _PARENT 仍不够（包名不对）
    # 改用直接修改模块系统：把 _PKG_DIR 注册为 'debate_agent' 包
    import importlib.util
    sys.path.insert(0, str(_PARENT))
    # 给 _PKG_DIR 的父建一个虚拟入口：直接把 _PKG_DIR 当 debate_agent 包加载
    spec = importlib.util.spec_from_file_location(
        "debate_agent", _PKG_DIR / "__init__.py",
        submodule_search_locations=[str(_PKG_DIR)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["debate_agent"] = mod
    spec.loader.exec_module(mod)
else:
    # (A) 标准布局
    sys.path.insert(0, str(_PARENT))

from debate_agent.core.moderator import Moderator
from debate_agent.core.events import Event
from debate_agent.core.exporter import build_markdown, save_markdown


st.set_page_config(page_title="新国辩 Agent", layout="wide",
                   initial_sidebar_state="expanded")

# ---------------- 样式 ----------------
st.markdown("""
<style>
.aff-bubble {
    background: #e8f4fd; border-left: 4px solid #1f77b4;
    padding: 12px 16px; border-radius: 6px; margin: 8px 0;
}
.neg-bubble {
    background: #fdecea; border-left: 4px solid #d62728;
    padding: 12px 16px; border-radius: 6px; margin: 8px 0;
}
.judge-reject {
    background: #fff3cd; border-left: 4px solid #f0ad4e;
    padding: 10px 14px; border-radius: 6px; margin: 8px 0;
    font-size: 0.9em;
}
.phase-header {
    background: #2c3e50; color: white; padding: 8px 16px;
    border-radius: 6px; margin: 16px 0 8px 0; font-weight: bold;
}
.speaker-tag { font-weight: bold; font-size: 0.95em; }
.aff-tag { color: #1f77b4; }
.neg-tag { color: #d62728; }
.judge-tag { color: #f0ad4e; }
.meta { color: #888; font-size: 0.8em; margin-bottom: 4px; }
</style>
""", unsafe_allow_html=True)


# ---------------- 侧边栏：配置 ----------------
with st.sidebar:
    st.title("⚖️ 新国辩 Agent")
    api_key = st.text_input(
        "DeepSeek API Key",
        value=os.environ.get("DEEPSEEK_API_KEY", ""),
        type="password",
        help="也可设环境变量 DEEPSEEK_API_KEY",
    )
    motion = st.text_input("辩题", value="人工智能的发展利大于弊")
    free_rounds = st.slider("自由辩论轮数 (每方)", 1, 6, 3)
    show_judge_drama = st.checkbox(
        "显示裁判介入过程", value=True,
        help="展示违规-修复全过程，关掉则只看最终通过的发言",
    )
    start_btn = st.button("🚀 开始辩论", type="primary",
                          use_container_width=True)
    st.divider()
    st.caption("规则：新国辩流程 · 立论→质询→驳论→自由辩论→结辩\n\n"
               "裁判实时校验：稻草人、偷换概念、新论据冻结、字数")


st.title(f"辩题：{motion}")


# ---------------- 渲染函数 ----------------
def render_speech(side: str | None, speaker_role: str, content: str,
                  forced: bool = False, container=None):
    """渲染一条已通过的发言。"""
    target = container if container is not None else st
    css = "aff-bubble" if side == "aff" else ("neg-bubble" if side == "neg" else "")
    tag_css = "aff-tag" if side == "aff" else ("neg-tag" if side == "neg" else "")
    badge = " <span style='color:#999'>(已强制通过)</span>" if forced else ""
    target.markdown(
        f"<div class='{css}'>"
        f"<div class='speaker-tag {tag_css}'>{speaker_role}{badge}</div>"
        f"<div style='margin-top:6px; white-space:pre-wrap'>{content}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_judge_reject(violations: list, fix_hint: str, attempt: int,
                        container=None):
    target = container if container is not None else st
    viols = "<br>".join(f"• {v}" for v in violations) or "(未列出)"
    target.markdown(
        f"<div class='judge-reject'>"
        f"<div class='speaker-tag judge-tag'>⚠ 裁判打回 (第 {attempt} 稿)</div>"
        f"<div class='meta'>违规：</div>{viols}"
        f"<div class='meta' style='margin-top:6px'>修改建议：</div>{fix_hint}"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_phase_header(speaker_role: str, container=None):
    target = container if container is not None else st
    target.markdown(
        f"<div class='phase-header'>📍 {speaker_role}</div>",
        unsafe_allow_html=True,
    )


def render_plan(side_name: str, plan: dict, color: str):
    """渲染一方的作战计划。"""
    st.markdown(f"### <span style='color:{color}'>{side_name}方作战计划</span>",
                unsafe_allow_html=True)
    st.markdown(f"**判准**：{plan.get('standard', '(无)')}")
    defs = plan.get("definitions", {})
    if defs:
        with st.expander("核心定义", expanded=False):
            for k, v in defs.items():
                st.markdown(f"- **{k}**：{v}")
    args = plan.get("main_arguments", [])
    if args:
        st.markdown("**核心论点**：")
        for a in args:
            st.markdown(f"- {a}")
    st.caption(f"📚 检索到 {plan.get('evidence_count', 0)} 条证据")


def render_verdict(verdict: dict):
    st.header("🏆 裁判评分")
    if "error" in verdict:
        st.error(f"评分解析失败: {verdict.get('error')}")
        st.code(verdict.get("raw", ""))
        return
    winner = verdict.get("winner")
    winner_name = "正方" if winner == "aff" else ("反方" if winner == "neg" else "?")
    conf = verdict.get("confidence", 0)
    st.success(f"**胜方：{winner_name}**　置信度 {conf:.0%}")
    st.markdown(f"**评判理由**：{verdict.get('verdict', '')}")

    scores = verdict.get("scores", {})
    if scores:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("#### 正方得分")
            for k, v in scores.get("aff", {}).items():
                st.markdown(f"- {k}: **{v}**")
        with col_b:
            st.markdown("#### 反方得分")
            for k, v in scores.get("neg", {}).items():
                st.markdown(f"- {k}: **{v}**")

    clashes = verdict.get("key_clashes", [])
    if clashes:
        st.markdown("#### 战场焦点")
        for c in clashes:
            w = c.get("winner", "")
            w_name = {"aff": "正方", "neg": "反方", "tie": "平"}.get(w, w)
            st.markdown(f"- **{c.get('issue','')}** → {w_name}：{c.get('reason','')}")


def render_review(review: dict):
    st.header("🎓 复盘建议")
    if "error" in review:
        st.error(f"复盘解析失败: {review.get('error')}")
        st.code(review.get("raw", ""))
        return
    col_a, col_b = st.columns(2)
    for col, key, name in [(col_a, "aff_review", "正方"),
                            (col_b, "neg_review", "反方")]:
        with col:
            r = review.get(key, {})
            st.markdown(f"#### {name}")
            if r.get("strengths"):
                st.markdown("**亮点**")
                for s in r["strengths"]:
                    st.markdown(f"- {s}")
            if r.get("missed_opportunities"):
                st.markdown("**错失机会**")
                for s in r["missed_opportunities"]:
                    st.markdown(f"- {s}")
            if r.get("tactical_suggestions"):
                st.markdown("**改进建议**")
                for s in r["tactical_suggestions"]:
                    st.markdown(f"- {s}")
    if review.get("best_moment"):
        st.markdown(f"✨ **最精彩瞬间**：{review['best_moment']}")
    if review.get("worst_moment"):
        st.markdown(f"💧 **最低质量瞬间**：{review['worst_moment']}")


# ---------------- 主流程 ----------------
if start_btn:
    if not api_key:
        st.error("请填写 DeepSeek API Key")
        st.stop()
    if not motion.strip():
        st.error("请输入辩题")
        st.stop()
    os.environ["DEEPSEEK_API_KEY"] = api_key

    # 作战计划区域（双栏占位）
    plan_col_a, plan_col_b = st.columns(2)
    plan_a_ph = plan_col_a.empty()
    plan_b_ph = plan_col_b.empty()

    st.divider()
    st.subheader("📜 辩论实时记录")
    progress_ph = st.empty()
    transcript_container = st.container()

    # 跑流式
    moderator = Moderator(motion=motion, free_debate_rounds=free_rounds,
                           verbose=False)
    current_phase_container = None
    phase_count = 0
    total_phases = 9 + 1  # 9 个环节 + 准备

    verdict_data = None
    review_data = None
    plans_data: dict = {}                # {"aff": {...}, "neg": {...}}
    transcript_data: list[dict] = []     # 累积所有已通过的发言

    try:
        for event in moderator.run_stream():
            kind = event.kind
            p = event.payload

            if kind == "debate_start":
                plans_data = {"aff": p.get("aff", {}), "neg": p.get("neg", {})}
                with plan_a_ph.container():
                    render_plan("正", p["aff"], "#1f77b4")
                with plan_b_ph.container():
                    render_plan("反", p["neg"], "#d62728")

            elif kind == "phase_start":
                phase_count += 1
                progress_ph.progress(
                    min(phase_count / total_phases, 1.0),
                    text=f"当前：{p.get('speaker_role', '')}",
                )
                with transcript_container:
                    render_phase_header(p.get("speaker_role", ""))
                    if p.get("evidence_frozen"):
                        st.info("🔒 证据池已冻结：本环节起不得引入新论据")

            elif kind == "speaking_start":
                if show_judge_drama and p.get("attempt", 1) > 1:
                    with transcript_container:
                        st.caption(f"🔄 {p.get('speaker_role','')} 正在重新生成 "
                                   f"(第 {p['attempt']} 稿)...")

            elif kind == "judge_rejected":
                if show_judge_drama:
                    with transcript_container:
                        render_judge_reject(
                            p.get("violations", []),
                            p.get("fix_hint", ""),
                            p.get("attempt", 1),
                        )

            elif kind == "speech_committed":
                transcript_data.append({
                    "phase": p.get("phase", ""),
                    "side": p.get("side"),
                    "speaker_role": p.get("speaker_role", ""),
                    "content": p.get("content", ""),
                })
                with transcript_container:
                    render_speech(
                        side=p.get("side"),
                        speaker_role=p.get("speaker_role", ""),
                        content=p.get("content", ""),
                        forced=p.get("forced", False),
                    )

            elif kind == "verdict":
                verdict_data = p.get("verdict", {})

            elif kind == "review":
                review_data = p.get("review", {})

            elif kind == "error":
                with transcript_container:
                    st.error(f"出错：{p.get('message')}")
                    with st.expander("traceback"):
                        st.code(p.get("traceback", ""))

            elif kind == "finished":
                progress_ph.progress(1.0, text="辩论完成 ✅")

    except Exception as e:
        st.error(f"运行异常：{e}")
        import traceback
        st.code(traceback.format_exc())

    # 终局
    if verdict_data is not None:
        st.divider()
        render_verdict(verdict_data)
    if review_data is not None:
        st.divider()
        render_review(review_data)

    # ---------- 保存 Markdown ----------
    if transcript_data:
        st.divider()
        st.subheader("💾 保存辩论记录")
        md_text = build_markdown(
            motion=motion,
            plans=plans_data,
            transcript=transcript_data,
            verdict=verdict_data,
            review=review_data,
        )
        save_path = save_markdown(motion, md_text, out_dir="debates")
        st.success(f"已保存至 `{save_path.resolve()}`")

        st.download_button(
            label=f"⬇️ 下载 {save_path.name}",
            data=md_text.encode("utf-8"),
            file_name=save_path.name,
            mime="text/markdown",
            use_container_width=True,
        )
        with st.expander("📄 预览 Markdown 内容"):
            st.code(md_text, language="markdown")

    st.balloons()
else:
    st.info("👈 在左侧填写 API Key 与辩题，点击 **开始辩论**")
    st.markdown("""
    ### 这是什么？
    一个按 **新国辩格式** 自动对抗的双 Agent 辩论系统。
    
    - 正反方各由一个 DeepSeek 辩手 Agent 扮演，立论前联网检索证据
    - 每条发言由 **裁判 Agent** 实时校验：稻草人、偷换概念、新论据冻结、字数
    - 不合规则打回重生成 (最多 3 稿)
    - 跑完后给出胜负判定、各维度评分、双方复盘建议
    
    ### 流程
    
    立论(正) → 立论(反) → 质询(正↔反) → 质询(反↔正) →
    驳论(正) → 驳论(反) → 自由辩论 → 结辩(反) → 结辩(正) → 评分 + 复盘
    """)
