"""`<ul>` / `<ol>` / `<dl>` 列表识别器（priority=40，最低）。

匹配条件：
- 节点是 `<ul>` / `<ol>` / `<dl>`；或祖先包含至少 2 个直接子 `<li>`/`<dt>`。

抽取：
- `<dl>`：两列 `(Key, Value)`；
- `<ul>` / `<ol>`：两列 `(Index, Text)`。
"""
from __future__ import annotations

from typing import List

from bs4 import Tag

from ..cleaner import clean_cell_node, clean_text
from ..schemas import ColumnDef, ExtractedCell, ExtractedControl, ExtractedRow, MatchCandidate
from .base import Recognizer, register


class ListBlockRecognizer(Recognizer):
    priority = 40

    def matches(self, node: Tag) -> bool:
        if not isinstance(node, Tag):
            return False
        if node.name in ("ul", "ol", "dl"):
            return True
        anc = node.parent
        while anc is not None and isinstance(anc, Tag):
            if anc.name in ("ul", "ol", "dl"):
                # 至少需要 2 个直接子项
                direct = anc.find_all(recursive=False)
                direct = [c for c in direct if c.name in ("li", "dt", "dd")]
                if len(direct) >= 2:
                    return True
            anc = anc.parent
        return False

    def extract(self, node: Tag, candidate: MatchCandidate) -> ExtractedControl:
        # 找最近的列表根
        root: Tag = node
        for anc in node.parents:
            if isinstance(anc, Tag) and anc.name in ("ul", "ol", "dl"):
                root = anc
                break

        ctrl = ExtractedControl(
            title=candidate.matched_text,
            matched_text=candidate.matched_text,
            source=candidate.source,
            control_type="list_block",
        )

        if root.name == "dl":
            ctrl.columns.extend([
                ColumnDef(key="Key", type="text", source="dt", index=0),
                ColumnDef(key="Value", type="text", source="dd", index=1),
            ])
            dts = root.find_all("dt", recursive=False)
            dds = root.find_all("dd", recursive=False)
            n = max(len(dts), len(dds))
            for i in range(n):
                key = clean_text(dts[i].get_text(" ", strip=True)) if i < len(dts) else ""
                val_cell = clean_cell_node(dds[i]) if i < len(dds) else ExtractedCell(value="", type="text")
                ctrl.rows.append(ExtractedRow(cells=[
                    ExtractedCell(value=key, type="text"),
                    val_cell,
                ]))
        else:
            ctrl.columns.extend([
                ColumnDef(key="Index", type="text", source="index", index=0),
                ColumnDef(key="Text", type="text", source="li", index=1),
            ])
            items = root.find_all("li", recursive=False)
            for idx, li in enumerate(items, 1):
                ctrl.rows.append(ExtractedRow(cells=[
                    ExtractedCell(value=str(idx), type="text"),
                    clean_cell_node(li),
                ]))

        if not ctrl.rows:
            ctrl.warnings.append("loading_or_empty")
            ctrl.rows.append(ExtractedRow(cells=[
                ExtractedCell(value="", type="text"),
                ExtractedCell(value="", type="text"),
            ]))

        return ctrl


register(ListBlockRecognizer())
