# 新国辩 Agent

基于 DeepSeek 的双辩手对抗系统，遵循新国辩流程，含检索、实时合规裁判、赛后复盘，以及 Streamlit 实时观看前端。

## 结构

```
debate_agent/
├── app.py                # ★ Streamlit 前端（流式观看）
├── main.py               # CLI 入口
├── core/
│   ├── state.py          # 辩论全局状态（共享 trace + 私有档案）
│   ├── phases.py         # 新国辩流程状态机
│   ├── events.py         # 流式事件类型
│   └── moderator.py      # 调度器（含 run() 与 run_stream()）
├── agents/
│   ├── debater.py
│   ├── judge.py
│   └── reviewer.py
├── tools/
│   ├── llm.py            # DeepSeek 客户端
│   └── search.py         # 联网检索 (RAG)
└── prompts/
```

## 依赖

```bash
pip install openai httpx tenacity streamlit duckduckgo-search
```

## 使用

### 方式 A：Streamlit 前端（推荐）

```bash
export DEEPSEEK_API_KEY="sk-..."
streamlit run debate_agent/app.py
```

浏览器打开后，左侧填辩题，点"开始辩论"，会**实时流式**显示：
- 双方赛前作战计划（判准、论点、证据数）
- 每个环节的发言（正方蓝色、反方红色气泡）
- 裁判打回时的违规列表与修改建议（黄色提示）
- 终局评分 + 双方复盘

### 方式 B：命令行

```bash
export DEEPSEEK_API_KEY="sk-..."
python -m debate_agent.main --motion "人工智能的发展利大于弊"
```
