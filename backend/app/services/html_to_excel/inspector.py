"""枚举 HTML 中所有可下载控件（SPEC §4.6 v0.2.0）。

- `HTMLInspector.inspect(soup) -> list[DetectedControl]`：扫描所有候选节点，
  经 recognizer.matches 过滤 + 显著过滤（§4.6.1），生成 ControlSummary 列表。
- `DetectedControl.control` 是已 extract 的完整 `ExtractedControl`，供 `run_by_index` 复用。
"""
from __future__ import annotations

from typing import List, Tuple

from bs4 import BeautifulSoup, Tag

from .cleaner import clean_text
from .recognizers import find_control_root
from .schemas import (
    ColumnDef,
    ControlPreview,
    ControlSummary,
    DetectedControl,
    ExtractedControl,
    ExtractedRow,
    MatchCandidate,
)


PREVIEW_N_ROWS = 3
PREVIEW_N_COLS = 5


# ────────────────────────────── 辅助判定 ──────────────────────────────


def _is_inner_of_nested_table(node: Tag) -> bool:
    """判定 node 是否是"嵌套数据表"的真实内层。

    仅当外层 <table> 自身有明显的数据行（`class` 含 `uir-machine-row` 或
    `tr_count >= 2` 且 column_count >= 2）才视为真正的嵌套；否则外层
    仅是 layout wrapper（HTML 解析器为补全破洞 HTML 强行加的），保留当前表。

    在 NetSuite 实际页面里，`<table id="item_splits">` 的祖先链虽然因
    lxml 自动补全包含一个 `<tbody><tr><td>...<table>...</table></td></tr></tbody>`
    但外层 wrapper 本身不含数据行；按本函数应保留 item_splits。
    """
    for a in node.parents:
        if not isinstance(a, Tag):
            return False
        if a.name == "table":
            # 外层是否真的算 "数据表"？
            if _is_real_data_table(a):
                return True
            # 外层是 wrapper → 当前表才是真正的兄弟表
            return False
        if a.name == "body":
            return False
    return False


def _is_real_data_table(table_node: Tag) -> bool:
    """外层 table 是否"真数据表"。

    NetSuite 把"tab 容器"也实现成 `<table>`，其 class 多含 `uir-tabs` /
    `uir-table-block`。这些不算数据表 → 当前节点不算内层。

    判断：
    1. class 含 `uir-tabs` 或 `uir-table-block` → 视为 tab/layout 外壳，跳过。
    2. 否则若行数 ≥ 2 且至少一行有 `uir-machine-row` / `uir-list-row` class → 数据表。
    3. 否则若首行 cell 数 ≥ 2 且非纯 th → 也算数据表。
    """
    table_cls = " ".join(table_node.get("class") or []).lower()
    if "uir-tabs" in table_cls or "uir-table-block" in table_cls or "uir-popup" in table_cls:
        return False

    trs = table_node.find_all("tr")
    if len(trs) < 2:
        return False
    for tr in trs:
        cls = " ".join(tr.get("class") or []).lower()
        if "uir-machine-row" in cls or "uir-list-row" in cls:
            return True
    first = trs[0]
    cells = first.find_all(["th", "td"], recursive=False)
    if len(cells) >= 2 and not all(c.name == "th" for c in cells):
        return True
    return False


def _is_loading_or_pure_header(table_node: Tag) -> bool:
    """单层 <table> 是否 Loading 占位 / 纯表头无数据。

    检查：表本身 class、任一 <tr> class、或者只有 1 行 tr 且全是 th。
    """
    classes = " ".join(table_node.get("class") or []).lower()
    if "loading-row" in classes or "nodata-row" in classes or "loading-table" in classes:
        return True
    trs = table_node.find_all("tr")
    if not trs:
        return True
    # 任一 tr 的 class 含 loading-row / nodata-row → 占位表
    for tr in trs:
        tr_cls = " ".join(tr.get("class") or []).lower()
        if "loading-row" in tr_cls or "nodata-row" in tr_cls:
            return True
    # 只有 1 行 tr 且全是 th（纯 header）
    if len(trs) == 1:
        only_tr = trs[0]
        cells = only_tr.find_all(["th", "td"], recursive=False)
        if cells and all(c.name == "th" for c in cells):
            return True
    return False


def _synthetic_candidate(root: Tag, source: str) -> MatchCandidate:
    return MatchCandidate(node=root, source=source, matched_text=root.name)


def _suggested_title(root: Tag) -> Tuple[str, str]:
    """启发式提标题，按 SPEC §4.6.2 优先级。"""
    # 1) 最近 th 文字
    th = root.find("th")
    if th is not None:
        t = clean_text(th.get_text(" ", strip=True))
        if t:
            return t, "thead-th"
    # 2) aria-label
    al = root.get("aria-label")
    if al and al.strip():
        return al.strip(), "aria-label"
    # 3) 上方最近的 h1-h6
    for h in ("h2", "h3", "h1", "h4", "h5", "h6"):
        sib = root.find_previous_sibling(h)
        if sib is not None:
            t = clean_text(sib.get_text(" ", strip=True))
            if t:
                return t, f"prev-{h}"
    # 4) legend 子（一般位于 fieldset 内）
    legend = root.find("legend")
    if legend is not None:
        t = clean_text(legend.get_text(" ", strip=True))
        if t:
            return t, "legend"
    # 5) id
    rid = root.get("id") or ""
    if rid:
        return rid, "id"
    return "", "fallback"


def _build_preview(control: ExtractedControl) -> ControlPreview:
    """从完整 ExtractedControl 截前 3 行 × 前 5 列做 preview。"""
    headers = [c.key for c in control.columns[:PREVIEW_N_COLS]]
    rows: list[list[str]] = []
    for row in control.rows[:PREVIEW_N_ROWS]:
        line: list[str] = []
        for cell in row.cells[:PREVIEW_N_COLS]:
            v = cell.value
            line.append("" if v is None else str(v))
        rows.append(line)
    return ControlPreview(headers=headers, first_rows=rows)


def _is_significant(control: ExtractedControl) -> bool:
    """SPEC §4.6.1 显著过滤。"""
    if control.row_count == 0:
        return False
    if control.column_count == 0 and control.control_type != "field_group":
        return False
    # field_group 至少要有 1 个字段
    if control.control_type == "field_group" and control.row_count == 0:
        return False
    return True


# ────────────────────────────── 主类 ──────────────────────────────


class HTMLInspector:
    """扫描 soup 中所有可下载控件。"""

    def inspect(self, soup: BeautifulSoup) -> list[DetectedControl]:
        """返回 list[DetectedControl]，按 DOM 顺序索引 0..N-1。"""
        collected: List[DetectedControl] = []
        seen_root_ids: set[int] = set()

        # 1) 所有 <table>
        for node in soup.find_all("table"):
            if _is_inner_of_nested_table(node):
                continue
            if _is_loading_or_pure_header(node):
                continue
            if self._try_register(node, "thead-th", collected, seen_root_ids):
                continue

        # 2) div role=table / rowgroup
        for node in soup.find_all(attrs={"role": ["table", "rowgroup"]}):
            self._try_register(node, "role-table", collected, seen_root_ids)

        # 3) legend（字段组 anchor）
        for node in soup.find_all("legend"):
            parent = node.find_parent(["form", "fieldset", "div"])
            if parent is not None:
                self._try_register(parent, "legend", collected, seen_root_ids)

        # 4) ul / ol / dl
        for node in soup.find_all(["ul", "ol", "dl"]):
            self._try_register(node, "list", collected, seen_root_ids)

        # 分配 stable index
        for idx, item in enumerate(collected):
            item.summary.index = idx
        return collected

    # ────────────────────────── 内部 ──────────────────────────

    def _try_register(self, node: Tag, source: str,
                      collected: list[DetectedControl],
                      seen_root_ids: set[int]) -> bool:
        """尝试注册一个候选控件。返回 True 表示成功注册（外部可据此跳过同名重复）。"""
        rec, root = find_control_root(node)
        if rec is None or root is None:
            return False
        if id(root) in seen_root_ids:
            return False
        try:
            control = rec.extract(root, _synthetic_candidate(root, source))
        except Exception:  # noqa: BLE001
            return False
        if not _is_significant(control):
            return False
        seen_root_ids.add(id(root))

        suggested, title_source = _suggested_title(root)
        summary = ControlSummary(
            index=0,  # 后置阶段重新编号
            control_type=control.control_type,
            suggested_title=suggested,
            title_source=title_source,
            row_count=control.row_count,
            column_count=control.column_count,
            preview=_build_preview(control),
        )
        collected.append(DetectedControl(summary=summary, node=root, control=control))
        return True
