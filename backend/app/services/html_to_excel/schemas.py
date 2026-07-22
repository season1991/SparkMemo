"""数据契约（SPEC §6）。

- 内部 dataclass：抽取阶段产出 `ExtractedControl` 系列；
- 公开 dataclass：流水线最终结果 `ExtractionResult`，可被 API/CLI 直接序列化。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# ────────────────────────────── 内部 dataclass ──────────────────────────────


@dataclass
class ExtractedCell:
    """单个单元格抽取结果。

    `value` 根据 `type` 选择类型：
    - text / status / tooltip / html: str
    - link: str（display text）
    - number / integer: float / int
    - date / datetime: str（原样保留，由 writer 决定格式）
    - boolean: bool
    """

    value: Any = None
    type: str = "text"
    href: str | None = None
    tooltip: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractedRow:
    """一行抽取结果。"""

    cells: list[ExtractedCell] = field(default_factory=list)
    is_subtotal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"cells": [c.to_dict() for c in self.cells], "is_subtotal": self.is_subtotal}


@dataclass
class ColumnDef:
    """一列的列定义。"""

    key: str = ""
    type: str = "text"
    source: str = ""
    index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractedControl:
    """一个被识别的控件完整抽取结果（SPEC §6.1）。"""

    title: str = ""
    matched_text: str = ""
    source: str = ""
    control_type: str = ""  # table | div_grid | field_group | list_block
    columns: list[ColumnDef] = field(default_factory=list)
    rows: list[ExtractedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "matched_text": self.matched_text,
            "source": self.source,
            "control_type": self.control_type,
            "columns": [c.to_dict() for c in self.columns],
            "rows": [r.to_dict() for r in self.rows],
            "warnings": list(self.warnings),
        }

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.columns)


# ────────────────────────────── 公开结果 dataclass ──────────────────────────────


@dataclass
class ExtractionResult:
    """流水线对外返回结构（SPEC §2.2 / §2.3）。

    `to_dict()` 的字段顺序与 SPEC §2.2 响应一致。
    """

    ok: bool = False
    error: str | None = None
    message: str | None = None
    candidates: list[str] | None = None
    control_type: str | None = None
    matched_title: str | None = None
    xlsx_path: str | None = None
    download_filename: str | None = None
    rows: int = 0
    columns: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "control_type": self.control_type,
            "matched_title": self.matched_title,
            "xlsx_path": self.xlsx_path,
            "download_filename": self.download_filename,
            "rows": self.rows,
            "columns": self.columns,
            "warnings": list(self.warnings),
            # 失败字段，None 字段不返回
            **({"error": self.error} if self.error else {}),
            **({"message": self.message} if self.message else {}),
            **({"candidates": list(self.candidates)} if self.candidates else {}),
        }


# ────────────────────────────── 候选节点（locator 内部）──────────────────────────────


@dataclass
class MatchCandidate:
    """标题定位阶段产出的候选节点（SPEC §4.2.4）。"""

    node: Any  # bs4.element.Tag（避免循环 import，类型提示见 locator）
    source: str
    matched_text: str
    parent_path: list[str] = field(default_factory=list)


# ────────────────────────────── v0.2.0 inspect 系列 ──────────────────────────────


@dataclass
class ControlPreview:
    """控件前 3 行 × 前 5 列预览（SPEC §4.6.3 / §2.5）。"""

    headers: list[str] = field(default_factory=list)
    first_rows: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"headers": list(self.headers), "first_rows": [list(r) for r in self.first_rows]}


@dataclass
class ControlSummary:
    """单个控件的摘要（对外响应 schema）。"""

    index: int = 0
    control_type: str = ""
    suggested_title: str = ""
    title_source: str = ""
    row_count: int = 0
    column_count: int = 0
    preview: ControlPreview = field(default_factory=ControlPreview)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "control_type": self.control_type,
            "suggested_title": self.suggested_title,
            "title_source": self.title_source,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "preview": self.preview.to_dict(),
        }


@dataclass
class DetectedControl:
    """inspect 内部数据结构。`control` 是完整 ExtractedControl（已 extract），

    供 `run_by_index` 复用，避免重复调用 recognizer.extract（节省 2s+）。
    """

    summary: ControlSummary = field(default_factory=ControlSummary)
    node: Any = None  # bs4.element.Tag
    control: "ExtractedControl" = None  # type: ignore[assignment]


@dataclass
class InspectionResult:
    """/inspect 端点的对外返回（SPEC §6.1.x）。"""

    ok: bool = False
    error: str | None = None  # html_unparseable | empty_html
    message: str | None = None
    html_size: int = 0
    controls: list[ControlSummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if self.ok:
            return {
                "ok": True,
                "html_size_kb": int(self.html_size / 1024),
                "controls": [c.to_dict() for c in self.controls],
            }
        d: dict[str, Any] = {"ok": False}
        if self.error:
            d["error"] = self.error
        if self.message:
            d["message"] = self.message
        return d
