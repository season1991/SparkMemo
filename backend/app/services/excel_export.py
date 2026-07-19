"""Excel 导出服务（v0.5.8）。

负责把查询结果转成 .xlsx 二进制流，供两个 export 端点复用：
- `GET /api/dsp-uploads/{id}/rows/export` → `build_dsp_rows_xlsx`
- `POST /api/pivot-query/export`        → `build_pivot_xlsx`

设计要点（与 spec §Excel 导出子模块 §6 对齐）：
1. 全部走 pandas + openpyxl，不引入样式美化、不做异步任务、不落盘
2. 时间戳 `_export_timestamp()` 输出 `YYYYMMDD_HHMMSS`，由 Python `datetime.now()` 生成
3. 公式注入防护 `_sanitize_formula`：首字符 ∈ `{=, +, -, @, \t, \r}` → 加单引号前缀
4. 列宽自适应 `_auto_width`：字符串长度 + 2，上限 50
5. 不依赖 DB / FastAPI，是纯函数模块，便于单测
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Iterable, Sequence

import pandas as pd
from openpyxl.utils import get_column_letter


# 公式注入触发字符（OWASP CSV Injection 思路，扩展到 Excel）
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")

# 列宽自适应上限
_MAX_WIDTH = 50


def _export_timestamp() -> str:
    """返回导出时刻的 `YYYYMMDD_HHMMSS` 字符串。

    不依赖 DB 日期函数；由 Python `datetime.now()` 生成。

    返回:
        str: 15 字符时间戳字符串，如 `"20260719_153045"`。
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _sanitize_formula(value: object) -> object:
    """公式注入防护：字符串首字符若是 `{=, +, -, @, \t, \r}` → 加单引号前缀。

    数值（int / float）原样返回；None 原样返回。

    参数:
        value: 待写入单元格的值。

    返回:
        object: 防护后的值。字符串前缀 `'`，其它原样返回。
    """
    if isinstance(value, str) and value and value[0] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


def _auto_width(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> list[float]:
    """列宽自适应：每列 = `max(len(header), max(len(str(cell)) for cell in col)) + 2`，上限 50。

    参数:
        headers: 表头列表。
        rows: 数据行列表（每行是 sequence）。

    返回:
        list[float]: 每列的 openpyxl `column_dimensions.width` 值。
    """
    widths: list[float] = []
    for col_idx, header in enumerate(headers):
        max_len = len(str(header))
        for row in rows:
            if col_idx < len(row):
                cell = row[col_idx]
                if cell is None:
                    continue
                max_len = max(max_len, len(str(cell)))
        widths.append(float(min(max_len + 2, _MAX_WIDTH)))
    return widths


def _apply_widths(ws, widths: Sequence[float]) -> None:
    """把列宽写入 openpyxl worksheet。"""
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width


def build_dsp_rows_xlsx(rows: Iterable) -> bytes:
    """构造「事实行」单 sheet xlsx。

    列顺序（spec §4.1，12 列）：
    ID / 上传批次ID / 国家 / 类别 / 配置代码 / 配置名称 / 数据类型 / TTL /
    年月 / 周编号 / 周起始日 / 数量

    参数:
        rows: `DspUploadRow` ORM 实例的可迭代对象。

    返回:
        bytes: xlsx 二进制内容。
    """
    headers = [
        "ID", "上传批次ID", "国家", "类别", "配置代码", "配置名称",
        "数据类型", "TTL", "年月", "周编号", "周起始日", "数量",
    ]

    data: list[list[object]] = []
    for r in rows:
        data.append([
            r.id,
            r.upload_id,
            _sanitize_formula(r.country if r.country is not None else ""),
            _sanitize_formula(r.category if r.category is not None else ""),
            _sanitize_formula(r.config_code if r.config_code is not None else ""),
            _sanitize_formula(r.config_name if r.config_name is not None else ""),
            _sanitize_formula(r.data_type if r.data_type is not None else ""),
            r.ttl if r.ttl is not None else "",
            r.ym,
            r.week,
            r.date,
            r.quantity,
        ])

    df = pd.DataFrame(data, columns=headers)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="事实行", index=False)
        ws = writer.sheets["事实行"]
        _apply_widths(ws, _auto_width(headers, data))
    return buf.getvalue()


def build_pivot_xlsx(req, resp) -> bytes:
    """构造透视结果 xlsx：sheet 1「透视结果」+ sheet 2「查询参数快照」。

    参数:
        req: `PivotQueryRequest` 实例。
        resp: `PivotQueryResponse` 实例（已由 `crud.pivot_query.query_pivot` 计算）。

    返回:
        bytes: xlsx 二进制内容。
    """
    # ---- sheet 1：透视结果 ----
    base_headers = ["国家", "类别", "配置代码", "配置名称", "数据类型", "TTL", "版本日期"]
    period_columns = list(resp.period_columns)
    headers = base_headers + period_columns

    data: list[list[object]] = []
    for row in resp.row_groups:
        line: list[object] = [
            _sanitize_formula(row.country if row.country is not None else ""),
            _sanitize_formula(row.category if row.category is not None else ""),
            _sanitize_formula(row.config_code if row.config_code is not None else ""),
            _sanitize_formula(row.config_name if row.config_name is not None else ""),
            _sanitize_formula(row.data_type if row.data_type is not None else ""),
            row.ttl if row.ttl is not None else "",
            row.version_date,
        ]
        for pd_ in period_columns:
            line.append(row.quantities.get(pd_, 0))
        data.append(line)

    df = pd.DataFrame(data, columns=headers)

    # ---- sheet 2：查询参数快照 ----
    snapshot_headers = ["pivot_type", "vendor", "item", "sub_item", "version_dates"]
    snapshot_data = [[
        req.pivot_type,
        req.vendor,
        req.item,
        req.sub_item,
        "; ".join(req.version_dates),
    ]]

    df_snap = pd.DataFrame(snapshot_data, columns=snapshot_headers)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="透视结果", index=False)
        _apply_widths(writer.sheets["透视结果"], _auto_width(headers, data))

        df_snap.to_excel(writer, sheet_name="查询参数快照", index=False)
        _apply_widths(
            writer.sheets["查询参数快照"],
            _auto_width(snapshot_headers, snapshot_data),
        )

    return buf.getvalue()