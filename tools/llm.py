"""DeepSeek 客户端。DeepSeek 提供 OpenAI 兼容 API，直接复用 openai SDK。

模型：
- deepseek-chat: 通用对话，用于辩手 / 复盘
- deepseek-reasoner: 推理增强，可用于裁判（更严的逻辑校验）

代理处理：
- 默认忽略环境里的 http_proxy / https_proxy / all_proxy（防止 socks:// 等
  非法 scheme 把 httpx 搞挂）。
- 若确需走代理，设 DEBATE_PROXY 环境变量，如:
    export DEBATE_PROXY=http://127.0.0.1:7890
    export DEBATE_PROXY=socks5://127.0.0.1:7897   # 需 pip install 'httpx[socks]'
"""
from __future__ import annotations
import os
import httpx
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


_client: OpenAI | None = None


def _build_http_client() -> httpx.Client:
    """返回一个不读环境代理的 httpx client。可选显式代理。"""
    explicit_proxy = os.environ.get("DEBATE_PROXY", "").strip() or None
    # trust_env=False 关键：忽略 http_proxy/https_proxy/all_proxy 等环境变量
    return httpx.Client(
        proxy=explicit_proxy,
        trust_env=False,
        timeout=httpx.Timeout(60.0, connect=10.0),
    )


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("请设置环境变量 DEEPSEEK_API_KEY")
        _client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            http_client=_build_http_client(),
        )
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def chat(
    system: str,
    user: str,
    model: str = "deepseek-chat",
    temperature: float = 0.7,
    max_tokens: int = 1500,
) -> str:
    """单轮对话。所有 Agent 都走这个接口。"""
    client = get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""
