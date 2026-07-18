"""DSP Excel 解析模块（v0.5）。

本模块是纯函数模块，不依赖 SQLAlchemy / FastAPI；可被路由层直接调用，也可被单测直接测试。

约定：
- 静态字段按**字面列号**读取：col 4=Country, 5=Category, 6=ConfigCode, 10=DataType, 11=TTL；
- col 12=Update By 仅作周列起点边界，不读不存；
- col 13+ 为周列；行 1 携带稀疏 `ym` 标签（前向传播），行 2 周编号，行 3 周起始日；
- 行 4+ 为数据行；行 4..max_row 全部参与 R1/R2 行级过滤。

跳过规则（与 spec §跳过规则 一一对应）：
- 行级：R1（Country+ConfigCode 同时空）、R2（DataType 不是 Demand/Supply）、R3（无有效周列）；
- 列级：C1（行 2 周编号空）、C2（行 3 周起始日空）、C3（无 ym）、C4（quantity 空/None/0）。

异常：
- SheetMissingError → 422
- BadQuantityError → 400
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Optional

import openpyxl


SHEET_NAME = "DSP"

COL_COUNTRY = 4
COL_CATEGORY = 5
COL_CONFIG_CODE = 6
COL_DATA_TYPE = 10
COL_TTL = 11
COL_UPDATE_BY = 12
COL_WEEK_START = 13

ROW_WEEK_NO = 2
ROW_WEEK_DATE = 3
ROW_DATA_START = 4

DATA_TYPES_KEPT = ("Demand", "Supply")


class SheetMissingError(Exception):
    """Sheet 名不是 'DSP' → 路由层映射 422。"""


class BadQuantityError(Exception):
    """quantity 含非数字字符串 / 非整数浮点 → 路由层映射 400。"""


@dataclass
class FactRow:
    """解析后的单条事实行。"""

    country: Optional[str]
    category: Optional[str]
    config_code: Optional[str]
    data_type: Optional[str]
    ttl: Optional[int]
    ym: str
    week: str
    date: str
    quantity: int


def parse_filename(filename: str) -> tuple[str, str, str]:
    """截掉扩展名后按 '-' 切分，返回前 3 段；段数 < 3 抛 ValueError。

    实现严格按 spec 给出的伪代码。

    **状态（v0.5.1）**：此函数**不再被** `POST /api/dsp-uploads` 调用——
    前端要求用户在 UI 内提供 vendor / item / sub_item，服务端仅校验与入库。
    本函数保留供以下场景使用：
    - 导入 / 迁移遗留脚本（spec 预留的「其他调用者」）；
    - 命令行调试工具；
    - 单元测试覆盖同名 spec §Test Plan §1 时的引用。
    后续如确认所有调用方都已迁移到 Form 字段，可安全删除本函数。
    """
    if not filename:
        raise ValueError("filename is required")
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    parts = stem.split("-")
    if len(parts) < 3:
        raise ValueError("filename must contain at least 3 segments separated by '-'")
    return parts[0], parts[1], parts[2]


def _cell_str(value) -> str:
    """统一把 cell 值转字符串并 strip；None 返回空串。"""
    if value is None:
        return ""
    return str(value).strip()


def _ym_propagation(ws) -> dict[int, str]:
    """行 1 col 13+ 的稀疏 `ym` 标签做前向传播。

    示例：行 1 = ['', '2025-01', '', '', '', '2025-02', '', '', '2025-03', ...]
    → {13:'2025-01', 14:'2025-01', 15:'2025-01', 16:'2025-01', 17:'2025-01',
       18:'2025-02', 19:'2025-02', 20:'2025-02', 21:'2025-03', ...}
    """
    result: dict[int, str] = {}
    current = ""
    for c in range(COL_WEEK_START, ws.max_column + 1):
        v = _cell_str(ws.cell(row=1, column=c).value)
        if v:
            current = v
        if current:
            result[c] = current
    return result


def _parse_ttl(value) -> Optional[int]:
    """TTL 容错：整数原样；浮点整数化；其它入 None（不阻断上传）。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            try:
                f = float(s)
            except ValueError:
                return None
            return int(f) if f.is_integer() else None
    return None


def _parse_quantity(value, *, row: int, col: int) -> Optional[int]:
    """解析 quantity；返回 None 表示跳过该 cell；抛 BadQuantityError 表示阻断。

    规则（C4）：
    - None / 空字符串 → 跳过
    - bool → 跳过（与 is True 视作 1 的情形混淆，保守跳过）
    - 整数 0 / 浮点 0.0 → 跳过
    - 整数 >0 / 浮点整数 >0 → 入库 int
    - 浮点非整数（如 1.5）→ 阻断（BadQuantityError）
    - 字符串：strip 后按 float 解析；非数字 → 阻断；整数化 → 入库；非整数浮点 → 阻断
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value != 0 else None
    if isinstance(value, float):
        if value == 0:
            return None
        if not value.is_integer():
            raise BadQuantityError(
                f"row {row} col {col}: quantity {value!r} is non-integer"
            )
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            f = float(s)
        except ValueError as exc:
            raise BadQuantityError(
                f"row {row} col {col}: quantity {value!r} is non-numeric"
            ) from exc
        if f == 0:
            return None
        if not f.is_integer():
            raise BadQuantityError(
                f"row {row} col {col}: quantity {value!r} is non-integer"
            )
        return int(f)
    raise BadQuantityError(
        f"row {row} col {col}: quantity {value!r} is unsupported type"
    )


def parse_excel(content: bytes) -> list[FactRow]:
    """解析 DSP Excel 字节流，返回展开后的事实行列表。

    抛出 SheetMissingError / BadQuantityError 由路由层映射为 422 / 400。
    """
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    if SHEET_NAME not in wb.sheetnames:
        wb.close()
        raise SheetMissingError(f"sheet '{SHEET_NAME}' not found")
    ws = wb[SHEET_NAME]

    try:
        ym_at_col = _ym_propagation(ws)

        # 有效周列：(col, week, date) 列表
        week_cols: list[tuple[int, str, str]] = []
        for c in sorted(ym_at_col.keys()):
            week_v = _cell_str(ws.cell(row=ROW_WEEK_NO, column=c).value)
            date_v = _cell_str(ws.cell(row=ROW_WEEK_DATE, column=c).value)
            if not week_v or not date_v:
                continue
            week_cols.append((c, week_v, date_v))

        facts: list[FactRow] = []

        # R3：如果完全没有有效周列，事实行集合必为空，但仍需迭代完避免遗留
        if not week_cols:
            return facts

        for r in range(ROW_DATA_START, ws.max_row + 1):
            country = _cell_str(ws.cell(row=r, column=COL_COUNTRY).value)
            config_code = _cell_str(ws.cell(row=r, column=COL_CONFIG_CODE).value)

            # R1：Country 与 Config Code 同时为空 → 整行跳过
            if not country and not config_code:
                continue

            data_type = _cell_str(ws.cell(row=r, column=COL_DATA_TYPE).value)
            # R2：Data Type 严格匹配 Demand/Supply
            if data_type not in DATA_TYPES_KEPT:
                continue

            category = _cell_str(ws.cell(row=r, column=COL_CATEGORY).value) or None
            ttl = _parse_ttl(ws.cell(row=r, column=COL_TTL).value)

            for c, week, date in week_cols:
                q_raw = ws.cell(row=r, column=c).value
                # C4：数量解析（None/空/0 跳过；非数字 → 阻断；非整数浮点 → 阻断）
                quantity = _parse_quantity(q_raw, row=r, col=c)
                if quantity is None:
                    continue
                facts.append(
                    FactRow(
                        country=country or None,
                        category=category,
                        config_code=config_code or None,
                        data_type=data_type,
                        ttl=ttl,
                        ym=ym_at_col[c],
                        week=week,
                        date=date,
                        quantity=quantity,
                    )
                )
        return facts
    finally:
        wb.close()