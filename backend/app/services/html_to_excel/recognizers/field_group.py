"""label/value 字段组识别器（priority=30）。

匹配条件之一：
- 节点是 `<fieldset>` / `<form>` / `<div data-nsps-label="…">` 包含多条 `uir-field-wrapper` 子节点；
- 节点是 `<legend>` / `<h1>`-`<h6>`，且其后紧跟着含 field-wrapper 的 sibling。

抽取：每行两列 `(Label, Value)`。
"""
from __future__ import annotations

from typing import Iterator, List, Optional

from bs4 import Tag

from ..cleaner import clean_cell_node, clean_text
from ..schemas import ColumnDef, ExtractedCell, ExtractedControl, ExtractedRow, MatchCandidate
from .base import Recognizer, register


def _iter_next_siblings(node: Tag) -> Iterator[Tag]:
    """从给定节点出发，依次返回它的 next_sibling（跳过非 Tag 节点）。"""
    cur = getattr(node, "next_sibling", None)
    while cur is not None:
        if isinstance(cur, Tag):
            yield cur
        cur = getattr(cur, "next_sibling", None)


def _get_field_group_root(node: Tag) -> Optional[Tag]:
    """向上爬升直到找到包含 `uir-field-wrapper` 的组容器。

    规则：遇到 `<table>` 就停——避免在 table 内部的 listheader/dottedlink 等被误归为字段组。
    """
    anc = node
    while anc is not None and isinstance(anc, Tag):
        if anc.name == "table":
            return None
        if anc.find("div", class_="uir-field-wrapper", attrs={"data-mode": "view"}):
            return anc
        anc = anc.parent
    return None


class FieldGroupRecognizer(Recognizer):
    priority = 30

    def matches(self, node: Tag) -> bool:
        if not isinstance(node, Tag):
            return False
        # 节点自身含 `uir-field-wrapper`：是字段组容器
        if node.find("div", class_="uir-field-wrapper", attrs={"data-mode": "view"}):
            return True
        # 邻近祖先含字段组（但不能跨越 table）
        if _get_field_group_root(node) is not None:
            return True
        # 节点本身是 `<dt>` / `<h1>`-`<h6>` / `<legend>`：必须是字段组的标题
        if node.name in ("h1", "h2", "h3", "h4", "h5", "h6", "legend", "dt"):
            # 自身子树里包含 uir-field-wrapper → 才算
            if node.find("div", class_="uir-field-wrapper", attrs={"data-mode": "view"}):
                return True
            # 紧跟字段组（下一个有效 sibling 含 uir-field-wrapper）
            for sib in _iter_next_siblings(node):
                if isinstance(sib, Tag):
                    if sib.find("div", class_="uir-field-wrapper", attrs={"data-mode": "view"}):
                        return True
                    break
            return False
        return False

    def extract(self, node: Tag, candidate: MatchCandidate) -> ExtractedControl:
        ctrl = ExtractedControl(
            title=candidate.matched_text,
            matched_text=candidate.matched_text,
            source=candidate.source,
            control_type="field_group",
        )
        ctrl.columns.extend([
            ColumnDef(key="Label", type="text", source="nsps-label", index=0),
            ColumnDef(key="Value", type="text", source="nsps-input", index=1),
        ])

        root = _get_field_group_root(node)
        if root is None:
            # 节点自己是 h1-h6：把整个 body 当字段组扫描
            if node.name in ("h1", "h2", "h3", "h4", "h5", "h6", "legend"):
                root = node
            else:
                root = node

        if not root:
            ctrl.warnings.append("loading_or_empty")
            ctrl.rows.append(ExtractedRow(cells=[
                ExtractedCell(value="", type="text"),
                ExtractedCell(value="", type="text"),
            ]))
            return ctrl

        fields = root.find_all("div", class_="uir-field-wrapper", attrs={"data-mode": "view"})
        if not fields:
            # 兜底：搜索邻近祖先
            walked = root
            while walked and not fields:
                walked = walked.parent
                if walked is None:
                    break
                fields = walked.find_all("div", class_="uir-field-wrapper", attrs={"data-mode": "view"})

        if not fields:
            ctrl.warnings.append("loading_or_empty")
            ctrl.rows.append(ExtractedRow(cells=[
                ExtractedCell(value="", type="text"),
                ExtractedCell(value="", type="text"),
            ]))
            return ctrl

        for fld in fields:
            label = (fld.get("data-nsps-label") or "").strip()
            if not label:
                a = fld.find("a")
                if a is not None:
                    label = clean_text(a.get_text(" ", strip=True))
            if not label:
                label = fld.get("data-field-name") or ""

            inp = fld.find("span", class_="uir-field") or fld.find(attrs={"data-nsps-type": "field_input"})
            value_cell = clean_cell_node(inp) if inp else ExtractedCell(value="", type="text")

            ctrl.rows.append(ExtractedRow(cells=[
                ExtractedCell(value=label, type="text"),
                value_cell,
            ]))

        return ctrl


register(FieldGroupRecognizer())
