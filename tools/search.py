"""联网检索。默认用 DuckDuckGo（免费、无需 key），失败时返回空列表，不阻塞辩论流程。

调用时机受控（见 phases.py 的 can_search 字段）：
- 立论、驳论前：允许
- 质询、自由辩论、结辩：禁止
"""
from __future__ import annotations
import uuid
from ..core.state import Evidence, Side


def _ddg_search(query: str, n: int = 5) -> list[dict]:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return []
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=n))
    except Exception:
        return []


def search_evidence(query: str, side: Side, n: int = 4) -> list[Evidence]:
    """检索证据，包装成 Evidence 对象，绑定到使用方。

    返回的 Evidence 应放入辩手的 unused_evidence。结辩前可用。
    """
    hits = _ddg_search(query, n=n)
    result: list[Evidence] = []
    for h in hits:
        result.append(Evidence(
            id=f"ev_{uuid.uuid4().hex[:8]}",
            side=side,
            claim=h.get("title", "")[:80],
            snippet=(h.get("body") or h.get("snippet") or "")[:400],
            source=h.get("href") or h.get("url") or "",
        ))
    return result
