"""标题定位器（SPEC §4.2）。

按优先级 1..7 遍历匹配候选，返回 `MatchCandidate` 列表。
- 完全相等（不区分大小写）；collapsed-space；
- 0 个匹配 → also collects "近似"（仅大小写/空格差异）作为建议。
"""
from __future__ import annotations

import re
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from .cleaner import normalize_for_compare
from .schemas import MatchCandidate


_CANDIDATE_SOURCES = (
    "th-text",
    "listheader-text",
    "dt-text",
    "caption-text",
    "legend-text",
    "h1-h6-text",
    "label-text",
    "aria-label",
    "title",
    "alt",
    "nsps-label",
)


class TitleLocator:
    """按 7 个优先级位置找标题候选（SPEC §4.2.2）。

    排序策略：
    - source 分数越小越优先（th > listheader > dt > caption > legend > h1-h6 > label > aria-label > title > alt > nsps-label）；
    - 节点祖先含 `<table>` 时分数 -50（含 table 优先）；
    - 节点祖先含 `<form id="..._main_form">` 字段组时分数 +20；
    - 最后按 DOM 出现顺序。
    """

    _SOURCE_SCORE = {
        "th-text": 10,
        "listheader-text": 11,
        "dt-text": 12,
        "caption-text": 13,
        "legend-text": 14,
        "h1-h6-text": 15,
        "label-text": 20,
        "aria-label": 25,
        "title": 26,
        "alt": 27,
        "nsps-label": 30,
    }

    def find(self, soup: BeautifulSoup, title: str) -> tuple[list[MatchCandidate], list[str]]:
        """返回 `(exact_matches, suggestions)`。

        - exact_matches：完全相等的候选（按"分数越低越优先"排序），≥1 时客户端可二选一；
        - suggestions：仅大小写/空格差异的近似命中（无 exact_matches 时供客户端提示）。
        """
        normalized_query = normalize_for_compare(title)
        exact: list[MatchCandidate] = []
        suggestions: list[str] = []

        # 不同优先级逐个源匹配
        for source in _CANDIDATE_SOURCES:
            exact.extend(self._find_by_source(soup, source, normalized_query))

        # 去重（按 id(node)）：保留 score 更小者
        unique: dict[int, MatchCandidate] = {}
        for m in exact:
            existing = unique.get(id(m.node))
            if existing is None or self._score(m) < self._score(existing):
                unique[id(m.node)] = m
        exact = list(unique.values())

        # 排序：score 升序；DOM 顺序仅作 tiebreak（O(N) 内，不会爆）
        # 注：为避免 soup.descendants O(N²) 遍历，对 matches 仅做 source + ancestor 打分排序
        # 候选数通常是个位数，源内顺序足够稳定（pipeline 默认取第一个）
        exact.sort(key=lambda m: self._score(m))

        # suggestions：扫描常见标签 + 属性，收集归一后接近 normalized_query 但不完全相等的
        if not exact:
            suggestions.extend(self._collect_close_matches(soup, normalized_query))

        return exact, suggestions[:10]

    @classmethod
    def _score(cls, cand: MatchCandidate) -> int:
        s = cls._SOURCE_SCORE.get(cand.source, 50)
        # 祖先含 `<table>`：得分 -50（强优先）
        ancestor_chain = list(cand.node.parents) if isinstance(cand.node, Tag) else []
        if any(isinstance(a, Tag) and a.name == "table" for a in ancestor_chain):
            s -= 50
        # 祖先含 `<form id="..._main_form">` 且非自定义 sublist：得分 +20（降权）
        for a in ancestor_chain:
            if isinstance(a, Tag) and (a.get("id") or "").endswith("_main_form"):
                s += 20
                break
        return s

    # ────────────────── 各 source 的具体匹配 ──────────────────

    def _find_by_source(self, soup: BeautifulSoup, source: str, query: str) -> list[MatchCandidate]:
        m: list[MatchCandidate] = []
        if source == "th-text":
            for th in soup.find_all("th"):
                t = normalize_for_compare(th.get_text(" ", strip=True))
                if t and t.lower() == query.lower():
                    m.append(self._mk(th, source, t))
        elif source == "listheader-text":
            # `<div class="listheader">TEXT</div>`
            for el in soup.find_all("div", class_=re.compile(r"listheader")):
                t = normalize_for_compare(el.get_text(" ", strip=True))
                if t and t.lower() == query.lower():
                    m.append(self._mk(el, source, t))
        elif source == "dt-text":
            for el in soup.find_all(["dt", "caption", "legend"]):
                t = normalize_for_compare(el.get_text(" ", strip=True))
                if t and t.lower() == query.lower():
                    m.append(self._mk(el, source, t))
        elif source == "caption-text":
            for el in soup.find_all("caption"):
                t = normalize_for_compare(el.get_text(" ", strip=True))
                if t and t.lower() == query.lower():
                    m.append(self._mk(el, source, t))
        elif source == "legend-text":
            for el in soup.find_all("legend"):
                t = normalize_for_compare(el.get_text(" ", strip=True))
                if t and t.lower() == query.lower():
                    m.append(self._mk(el, source, t))
        elif source == "h1-h6-text":
            for el in soup.find_all(re.compile(r"^h[1-6]$")):
                t = normalize_for_compare(el.get_text(" ", strip=True))
                if t and t.lower() == query.lower():
                    m.append(self._mk(el, source, t))
        elif source == "label-text":
            for el in soup.find_all("label"):
                t = normalize_for_compare(el.get_text(" ", strip=True))
                if t and t.lower() == query.lower():
                    m.append(self._mk(el, source, t))
        elif source == "aria-label":
            for el in soup.find_all(True, attrs={"aria-label": True}):
                v = el.get("aria-label")
                t = normalize_for_compare(v or "")
                if t and t.lower() == query.lower():
                    m.append(self._mk(el, source, t))
        elif source == "title":
            for el in soup.find_all(True, attrs={"title": True}):
                v = el.get("title")
                t = normalize_for_compare(v or "")
                if t and t.lower() == query.lower():
                    m.append(self._mk(el, source, t))
        elif source == "alt":
            for el in soup.find_all(True, attrs={"alt": True}):
                v = el.get("alt")
                t = normalize_for_compare(v or "")
                if t and t.lower() == query.lower():
                    m.append(self._mk(el, source, t))
        elif source == "nsps-label":
            # NetSuite 字段 label：`data-nsps-label` 属性相等
            for el in soup.find_all(True, attrs={"data-nsps-label": True}):
                v = el.get("data-nsps-label")
                if not v:
                    continue
                t = normalize_for_compare(v)
                if t and t.lower() == query.lower():
                    m.append(self._mk(el, source, v))
        return m

    # ────────────────── 候选构造 ──────────────────

    @staticmethod
    def _mk(node: Tag, source: str, matched_text: str) -> MatchCandidate:
        ancestors = [a.name for a in node.parents if isinstance(a, Tag)][:6]
        return MatchCandidate(node=node, source=source, matched_text=matched_text, parent_path=ancestors)

    # ────────────────── 近似建议 ──────────────────

    def _collect_close_matches(self, soup: BeautifulSoup, query: str) -> list[str]:
        seen: dict[str, None] = {}
        ql = query.lower()
        for el in soup.find_all(["th", "td", "div", "a", "h1", "h2", "h3", "h4", "h5", "h6", "legend", "dt", "caption"]):
            text = normalize_for_compare(el.get_text(" ", strip=True))
            if not text or text.lower() == ql:
                continue
            if self._is_close(text, ql) and text not in seen:
                seen[text] = None
        return list(seen.keys())

    @staticmethod
    def _is_close(a: str, b: str) -> bool:
        """近似：大小写不敏感且最短编辑距离 ≤ 2。"""
        if abs(len(a) - len(b)) > 2:
            return False
        al, bl = a.lower(), b.lower()
        if al == bl:
            return True
        # 简单 DP：最多 2 步
        if len(al) > len(bl):
            al, bl = bl, al
        # Levenshtein distance ≤ 2
        prev2 = list(range(len(bl) + 1))
        prev1 = prev2[:]
        for i, ca in enumerate(al, 1):
            cur = [i] + [0] * len(bl)
            for j, cb in enumerate(bl, 1):
                cost = 0 if ca == cb else 1
                cur[j] = min(prev1[j] + 1, cur[j - 1] + 1, prev1[j - 1] + cost)
            prev2, prev1 = prev1, cur
            if min(prev1) > 2:
                return False
        return prev1[-1] <= 2


def select_first(candidates: list[MatchCandidate]) -> Optional[MatchCandidate]:
    """默认策略：选 candidates 第一个。调用方可用 name=`select_first` 替换为二选一策略。"""
    return candidates[0] if candidates else None
