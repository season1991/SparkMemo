"""div-based 重复行表格（priority=20）。

典型场景：Ant Design / Bootstrap / Material 等前端框架用 `<div role="table">` + `<div role="row">` 模拟表格。

识别条件：
- `node` 是任意祖先；
- 祖先链中存在 `<div role="table">` 或 `<div role="rowgroup">`；
- 直接子集里 ≥ 2 个兄弟同级 `<div role="row">`。

抽取：列定义从首行子元素的子结构推断（class 含 `columnheader` / `data-label`），数据行取所有同级 row。
"""
from __future__ import annotations

from typing import List

from bs4 import Tag

from ..cleaner import clean_cell_node, clean_text
from ..schemas import ColumnDef, ExtractedCell, ExtractedControl, ExtractedRow, MatchCandidate
from .base import Recognizer, register


_COL_TAG = "div"
_COL_ROLE = "row"
_HEADER_ROLE = "columnheader"


def _has_role(node: Tag, role: str) -> bool:
    return isinstance(node, Tag) and (node.get("role") or "") == role


def _div_with_role_above(node: Tag, target_role: str):
    """返回 node 自身或最近祖先中 `role == target_role` 的节点；含 node 自身。"""
    if _has_role(node, target_role):
        return node
    for anc in node.parents:
        if _has_role(anc, target_role):
            return anc
    return None


class DivGridRecognizer(Recognizer):
    priority = 20

    def matches(self, node: Tag) -> bool:
        if not isinstance(node, Tag):
            return False
        # 节点本身或祖先是 rowgroup/table + 有足够 row
        if _has_role(node, "rowgroup") or _has_role(node, "table"):
            return self._has_enough_rows(node)
        for anc in node.parents:
            if _has_role(anc, "rowgroup") or _has_role(anc, "table"):
                return self._has_enough_rows(anc)
        return False

    @staticmethod
    def _has_enough_rows(container: Tag) -> bool:
        rows = container.find_all("div", recursive=False, attrs={"role": "row"})
        return len(rows) >= 2

    def extract(self, node: Tag, candidate: MatchCandidate) -> ExtractedControl:
        ctrl = ExtractedControl(
            title=candidate.matched_text,
            matched_text=candidate.matched_text,
            source=candidate.source,
            control_type="div_grid",
        )

        # 找到最近的 grid 容器
        grid_root = _div_with_role_above(node, "rowgroup")
        if grid_root is None:
            grid_root = _div_with_role_above(node, "table") or node.find_parent("body")

        rows = grid_root.find_all("div", recursive=False, attrs={"role": "row"})

        # 抽取列名：第一个含 columnheader 的 row 作为 header
        cols: List[str] = []
        data_rows: list = list(rows)
        header_row = None
        for r in rows:
            chs = r.find_all(attrs={"role": _HEADER_ROLE})
            if chs:
                header_row = r
                cols = [clean_text(ch.get_text(" ", strip=True)) for ch in chs]
                data_rows.remove(r)
                break
        if not cols:
            # 没有 columnheader：从第一行 cell 数推断
            first = rows[0] if rows else None
            cells_in_first = first.find_all("div", recursive=False) if first else []
            cols = [f"column_{i}" for i in range(len(cells_in_first))]
            # 仍然去掉第一行作为 header 兜底
            if rows:
                data_rows = rows[1:]

        for idx, name in enumerate(cols):
            ctrl.columns.append(ColumnDef(key=name or f"column_{idx}", type="text", source="role-columnheader", index=idx))

        for tr in data_rows:
            cell_containers = tr.find_all("div", recursive=False)
            row = ExtractedRow(cells=[])
            for c in cell_containers[: len(ctrl.columns)]:
                row.cells.append(clean_cell_node(c))

            # 补齐
            while len(row.cells) < len(ctrl.columns):
                row.cells.append(ExtractedCell(value="", type="text"))

            # 截断
            row.cells = row.cells[: len(ctrl.columns)]
            ctrl.rows.append(row)

        if not ctrl.rows:
            ctrl.warnings.append("loading_or_empty")
            ctrl.rows.append(ExtractedRow(cells=[ExtractedCell(value="", type="text") for _ in cols] or []))

        return ctrl


register(DivGridRecognizer())
