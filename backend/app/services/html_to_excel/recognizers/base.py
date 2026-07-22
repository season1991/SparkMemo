"""识别器抽象基类 + 注册表（SPEC §4.3）。

- Recognizer 基类定义了 `matches` / `extract`；
- `REGISTRY` 维护所有具体识别器；
- `find_control_root` 接收命中节点，按 priority 爬升找祖先，找不到时尝试向下找兄弟/后继节点。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Iterable

from bs4 import Tag

from ..schemas import ExtractedControl

if TYPE_CHECKING:
    from ..schemas import MatchCandidate


class Recognizer(ABC):
    """识别器基类。

    子类必须实现：
    - `priority: int` —— 越小越优先；
    - `matches(node)` —— 当前祖先节点是否就是我们要抽取的根；
    - `extract(node, candidate)` —— 真正抽 ExtractedControl。
    """

    priority: int = 100

    @abstractmethod
    def matches(self, node: Tag) -> bool: ...

    @abstractmethod
    def extract(self, node: Tag, candidate: "MatchCandidate") -> ExtractedControl: ...


REGISTRY: list[Recognizer] = []


def register(recognizer: Recognizer) -> Recognizer:
    """把识别器加入全局注册表（按 priority 升序）。"""
    REGISTRY.append(recognizer)
    REGISTRY.sort(key=lambda r: r.priority)
    return recognizer


def find_control_root(node: Tag, soup=None):
    """从 `node` 向上爬升，找到第一个匹配的识别器 + 根节点。

    找不到时的兜底：
    1. 优先看 `node` 自身是否是 h1-h6 / legend——若是，向下找直接后继里最近的 table / div_grid / list；
    2. 再不行返回 (None, None)。
    """
    # 节点自身也算
    candidates = [node, *list(node.parents)]
    for anc in candidates:
        if not isinstance(anc, Tag):
            continue
        for rec in REGISTRY:
            if rec.matches(anc):
                return rec, anc

    # 兜底 1：h1-h6 / legend 节点下方紧跟的 table / grid / list
    if isinstance(node, Tag) and node.name in ("h1", "h2", "h3", "h4", "h5", "h6", "legend"):
        sib_or_me = _first_table_or_grid_after(node)
        if sib_or_me is not None:
            for rec in REGISTRY:
                if rec.matches(sib_or_me):
                    return rec, sib_or_me

    return None, None


def _first_table_or_grid_after(node: Tag) -> Tag | None:
    """从 node 开始向下找下一个同级或后继的 `<table>` / `role="rowgroup"` / `<ul>`/`<ol>`/`<dl>`。"""
    if not isinstance(node, Tag):
        return None
    # 1) node 自身是 table/grid/list
    for rec in REGISTRY:
        if rec.matches(node):
            return node

    # 2) 向下递归找子节点中最近的 table
    def _walk(n):
        for c in n.children:
            if isinstance(c, Tag):
                for rec in REGISTRY:
                    if rec.matches(c):
                        return c
                m = _walk(c)
                if m is not None:
                    return m
        return None

    m = _walk(node)
    if m is not None:
        return m

    # 3) 同级后继（next siblings）
    nxt = getattr(node, "next_sibling", None)
    while nxt is not None:
        if isinstance(nxt, Tag):
            for rec in REGISTRY:
                if rec.matches(nxt):
                    return nxt
            # 进入子树找
            m = _walk(nxt)
            if m is not None:
                return m
        nxt = getattr(nxt, "next_sibling", None)

    # 4) 祖先链的同级后继
    parent = node.parent
    while parent is not None and isinstance(parent, Tag):
        nxt = getattr(parent, "next_sibling", None)
        while nxt is not None:
            if isinstance(nxt, Tag):
                m = _walk(nxt)
                if m is not None:
                    return m
                for rec in REGISTRY:
                    if rec.matches(nxt):
                        return nxt
            nxt = getattr(nxt, "next_sibling", None)
        parent = parent.parent

    return None


def get_registry() -> Iterable[Recognizer]:
    return tuple(REGISTRY)
