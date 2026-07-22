"""文本/HTML 实体清洗（SPEC §4.4.1）。

- `clean_text`：归一空白、解码 HTML 实体；
- `clean_cell_node`：根据节点结构推断类型并返回 `ExtractedCell`；
- `infer_type`：根据 string 内容嗅探列类型（数字/日期/日期时间/布尔/链接）。
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

from bs4 import NavigableString, Tag

from .schemas import ExtractedCell


# ───────────────────────────── 文本归一化 ─────────────────────────────


_NBSP = "\xa0"
_WHITESPACE = re.compile(r"[\u2002\u2003\u2009\u202f]+")
_MULTI_NEWLINE = re.compile(r"\n{2,}")


def clean_text(s: str) -> str:
    """归一空白、HTML 实体反转（用于比对/回填纯文本）。

    规则：
    - `&nbsp;` / U+00A0 全部归为 ASCII 空格；
    - 合并多个空白为单空格；
    - `html.unescape` 解码 `&amp;` 等；
    - strip 首尾空白。
    """
    if not s:
        return ""
    s = s.replace(_NBSP, " ")
    s = s.replace("\u200b", "")  # zero-width space
    s = _WHITESPACE.sub(" ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = _MULTI_NEWLINE.sub("\n", s)
    return s.strip()


def normalize_for_compare(s: str) -> str:
    """标题比对归一：去多余空白 + strip，不区分大小写时调用方决定。"""
    return " ".join(clean_text(s).split())


# ───────────────────────────── 单元格清洗 ─────────────────────────────


def clean_cell_node(node: Tag | NavigableString | None) -> ExtractedCell:
    """对单个 `<td>` / `<span>` / `<div>` 节点做类型推断 + 内容抽取。

    返回 `ExtractedCell`（SPEC §6.1）。
    """
    if node is None:
        return ExtractedCell(value="", type="text")

    if isinstance(node, NavigableString):
        txt = clean_text(str(node))
        if not txt:
            return ExtractedCell(value="", type="text")
        return ExtractedCell(value=txt, type=infer_type(txt))

    if not isinstance(node, Tag):
        return ExtractedCell(value="", type="text")

    # 1) 复选框 / unck：img alt="Checked"/"Unchecked"
    checkbox_cell = _detect_checkbox(node)
    if checkbox_cell is not None:
        return checkbox_cell

    # 2) truncated `<span class="uir-field-truncated-value">(more...)</span>`：回填 tooltip
    trunc_node = node
    if isinstance(trunc_node, Tag) and "uir-field-truncated-value" in (trunc_node.get("class") or []):
        pass
    else:
        trunc_node = node.find("span", class_="uir-field-truncated-value")
    if trunc_node is not None and trunc_node.has_attr("data-ns-tooltip"):
        return ExtractedCell(value=trunc_node["data-ns-tooltip"], type="tooltip")

    # 3) 链接优先：内部 `<a class="dottedlink">TEXT</a>` → link
    a = node.find("a", class_="dottedlink")
    if a is not None:
        text = clean_text(a.get_text(" "))
        href = a.get("href") or ""
        if not text:
            return ExtractedCell(value="", type="text")
        return ExtractedCell(value=text, type="link", href=href)

    # 4) 状态块：`<div style="background-color:green;">` → OK/Alert 字符串
    status_cell = _detect_status(node)
    if status_cell is not None:
        return status_cell

    # 5) 普通文本节点（保留 <br> 为换行）
    text = node.get_text("\n", strip=False)
    text = clean_text(text)
    if not text:
        return ExtractedCell(value="", type="text")
    return ExtractedCell(value=text, type=infer_type(text))


def _detect_checkbox(node: Tag) -> ExtractedCell | None:
    """识别 NetSuite 风格的 checked/unchecked 复选框。"""
    # look for an image with alt="Checked"/"Unchecked", or parent class
    for img in node.find_all("img"):
        alt = img.get("alt")
        if alt == "Checked":
            return ExtractedCell(value=True, type="boolean")
        if alt == "Unchecked":
            return ExtractedCell(value=False, type="boolean")
    cls = node.get("class") or []
    joined = " ".join(cls).lower()
    if "checkbox_read_ck" in joined:
        return ExtractedCell(value=True, type="boolean")
    if "checkbox_read_unck" in joined:
        return ExtractedCell(value=False, type="boolean")
    return None


_STATUS_COLORS: dict[str, str] = {
    "green": "OK",
    "lime": "OK",
    "red": "Alert",
    "orange": "Warning",
    "yellow": "Warning",
    "gray": "Neutral",
    "grey": "Neutral",
}


def _detect_status(node: Tag) -> ExtractedCell | None:
    """`<div style="background-color:green;">&nbsp;</div>` → OK。"""
    divs = node.find_all("div", style=True)
    divs.append(node) if (node.name == "div" and node.get("style")) else None
    for div in divs:
        style = div.get("style", "")
        m = re.search(r"background-color\s*:\s*([a-zA-Z]+)", style, flags=re.I)
        if m:
            color = m.group(1).strip().lower()
            label = _STATUS_COLORS.get(color, color.capitalize())
            # 仅当 div 内文本是空白 → 当作状态色块
            inner_text = clean_text(div.get_text(" "))
            if not inner_text:
                return ExtractedCell(value=label, type="status")
    return None


# ───────────────────────────── 类型推断 ─────────────────────────────


_DATE_M_D_YYYY = re.compile(r"\b(0?[1-9]|1[0-2])\/(0?[1-9]|[12]\d|3[01])\/\d{2,4}\b")
_DATETIME_M_D_YYYY_H = re.compile(
    r"\b(0?[1-9]|1[0-2])\/(0?[1-9]|[12]\d|3[01])\/\d{2,4}\b\s+\d{1,2}:\d{2}\s*(am|pm|AM|PM)?"
)
_INT_RE = re.compile(r"^-?\d{1,10}$")
_FLOAT_RE = re.compile(r"^-?(\d{1,3}(,\d{3})+|\d+)?(\.\d+)?$")


def infer_type(text: str) -> str:
    """根据文本内容嗅探类型。失败默认 `text`。

    优先级：datetime > date > integer > number > 其他 → text
    """
    if not text:
        return "text"

    if _DATETIME_M_D_YYYY_H.match(text):
        return "datetime"

    if _DATE_M_D_YYYY.match(text):
        return "date"

    # Boolean（少见在 view 模式；带括号 True/False 字面）
    if text in ("TRUE", "FALSE"):
        return "boolean"

    # 数字嗅探（千分位形式：12,345.67）
    stripped = text.replace(",", "").strip()
    if _INT_RE.match(stripped):
        return "integer"
    if _FLOAT_RE.match(text):
        return "number"

    return "text"


# ───────────────────────────── 解析数值 ─────────────────────────────


def parse_number(text: str) -> float | int | None:
    """把 '751,653.00' / '34' 解析成 number/int；失败返回 None。"""
    if not text:
        return None
    t = text.replace(",", "").strip().rstrip("%")
    try:
        if "." not in t:
            return int(t)
        return float(t)
    except ValueError:
        return None


def parse_date(text: str) -> datetime | None:
    """尝试解析 M/d/yyyy 或 M/d/yyyy h:mm am/pm；失败返回 None。"""
    formats = ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M", "%m/%d/%Y")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None
