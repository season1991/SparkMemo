"""原生 `<table>` 识别器（priority=10，最高优先）。

识别条件：`node` 是 `<table>` 元素；自带 thead/tbody/tfoot（如有）。

抽取内容：
- 列定义从 `<thead>` 或首个 `<tr>` 取；
- 数据行从 `<tbody>` 取；
- footer 行（`<tfoot>` 或 class 含 totals/subtotal）按普通行追加末尾并标记 `is_subtotal=True`；
- 嵌套 `<table>` 单元格：占位 `(subtable, N rows)` 字符串。
"""
from __future__ import annotations

import re
from typing import List, Optional

from bs4 import Tag

from ..cleaner import clean_cell_node, clean_text
from ..schemas import ColumnDef, ExtractedControl, ExtractedRow, MatchCandidate
from .base import Recognizer, register


_TOTAL_CLASS_HINTS = ("totallingtable", "uir-list-row-total", "listtotal", "uitotallingrow", "totals-row")
_SUBTOTAL_KEYWORDS = ("subtotal", "sub-total", "total", "sum")


class TableRecognizer(Recognizer):
    priority = 10

    def matches(self, node: Tag) -> bool:
        return isinstance(node, Tag) and node.name == "table"

    def extract(self, node: Tag, candidate: MatchCandidate) -> ExtractedControl:
        ctrl = ExtractedControl(
            title=candidate.matched_text,
            matched_text=candidate.matched_text,
            source=candidate.source,
            control_type="table",
        )

        # 列定义
        headers = self._extract_headers(node)
        for idx, h in enumerate(headers):
            ctrl.columns.append(ColumnDef(key=h or f"column_{idx}", type="text", source="th", index=idx))

        # 数据行（thead 不再作为数据行）
        body_rows = self._data_rows(node)
        if not body_rows:
            ctrl.warnings.append("loading_or_empty")
            # 即便空，依然追加一行占位
            empty_row = ExtractedRow()
            empty_row.cells = [
                _empty_cell_for_col(c.key) for c in ctrl.columns
            ]
            ctrl.rows.append(empty_row)
            return ctrl

        for tr in body_rows:
            row = self._build_row(tr, len(ctrl.columns))
            ctrl.rows.append(row)

        return ctrl

    # ─────────────────── header 抽取 ───────────────────

    def _extract_headers(self, table_node: Tag) -> List[str]:
        """列名解析：从 thead 第一个 tr 取；否则从第一个 tr 取；否则 Column_0 占位。"""
        thead = table_node.find("thead")
        if thead:
            tr = thead.find("tr")
            if tr:
                texts = [self._cell_text(td) for td in tr.find_all(["th", "td"], recursive=False)]
                if any(texts):
                    return texts

        # 第一个 tr 作为表头
        first_tr = table_node.find("tr")
        if first_tr:
            texts = [self._cell_text(td) for td in first_tr.find_all(["th", "td"], recursive=False)]
            if any(texts):
                return texts

        # 用第一行数据单元数推断
        first_data = self._first_data_tr(table_node)
        if first_data:
            cols = first_data.find_all(["td", "th"], recursive=False)
            return [f"column_{i}" for i in range(len(cols))]

        return []

    @staticmethod
    def _first_data_tr(table_node: Tag) -> Optional[Tag]:
        tbody = table_node.find("tbody")
        if tbody:
            return tbody.find("tr")
        return table_node.find("tr")

    def _data_rows(self, table_node: Tag) -> List[Tag]:
        """提取数据行：跳过表头/加载占位/No records 占位，且不重复（不跨 tbody+table）。

        策略：以 `<table>` 为根做一次 `find_all("tr", recursive=True)`，跳过：
        - class 含 headerrow / loading-row / nodata-row 的行；
        - 只含 `<th>` 元素而没有 `<td>` 的行（典型 headerrow）。
        """
        rows: List[Tag] = []
        seen_ids: set[int] = set()
        for tr in table_node.find_all("tr"):
            if id(tr) in seen_ids:
                continue
            seen_ids.add(id(tr))
            cls = tr.get("class") or []
            joined = " ".join(cls).lower()
            if any(hint in joined for hint in ("headerrow", "loading-row", "nodata-row")):
                continue
            children = tr.find_all(["th", "td"], recursive=False)
            if children and all(c.name == "th" for c in children):
                # 头行：跳过（已在表头里）
                continue
            rows.append(tr)
        return rows

    def _build_row(self, tr: Tag, ncols: int) -> ExtractedRow:
        is_total_row = self._is_total_row(tr)
        tds = tr.find_all(["td", "th"], recursive=False)
        cells = []
        for td in tds[:ncols] if ncols else tds:
            # 嵌套 table：单元格内如果是另一张表 → 占位字符串
            inner = td.find("table")
            if inner is not None:
                inner_rows = inner.find_all("tr")
                place = f"(subtable, {len(inner_rows)} rows)"
                cells.append(__import__("app.services.html_to_excel.schemas", fromlist=["ExtractedCell"]).ExtractedCell(value=place, type="text"))
                continue
            cells.append(clean_cell_node(td))

        # 行长度对齐列数（少于则补空，多则截断）
        if ncols:
            if len(cells) < ncols:
                for _ in range(ncols - len(cells)):
                    cells.append(_empty_cell())
            elif len(cells) > ncols:
                cells = cells[:ncols]

        return ExtractedRow(cells=cells, is_subtotal=is_total_row)

    @staticmethod
    def _is_total_row(tr: Tag) -> bool:
        cls = tr.get("class") or []
        joined = " ".join(cls).lower()
        if any(hint in joined for hint in _TOTAL_CLASS_HINTS):
            return True
        # 用 row 的文案嗅探
        text = clean_text(tr.get_text(" ", strip=True)).lower()
        return any(k in text for k in _SUBTOTAL_KEYWORDS)

    @staticmethod
    def _cell_text(td: Tag) -> str:
        return clean_text(td.get_text(" ", strip=True))


def _empty_cell():
    from ..schemas import ExtractedCell
    return ExtractedCell(value="", type="text")


def _empty_cell_for_col(_col_name: str):
    return _empty_cell()


# self-register
register(TableRecognizer())
