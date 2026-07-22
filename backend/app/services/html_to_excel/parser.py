"""HTML 解析与降噪（SPEC §4.1）。

- 使用 `lxml` 解析器（容错强，对 NetSuite 这种残破结构友好）；
- 移除脚本/样式/SVG/IMG/iframe/巨型 JSON 配置块；
- 移除含 `noprint` / `uir-button` 等装饰 class 的节点；
- 移除非业务 div（页眉、超时遮罩等）。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup, Comment, Tag


# 一次性脚本/样式/SVG/IMG/noscript/iframe 节点标签
_NOISE_TAGS: tuple[str, ...] = ("script", "style", "noscript", "svg", "iframe")

# NetSuite 页面里"巨型 JSON 配置块"的特征：script 文本里包含一个超长 `{...}` 字面量
# 阈值保守为 1KB，避免误伤正常脚本
_HUGE_JSON_THRESHOLD = 1000
_HUGE_JSON_PATTERN = re.compile(r"\{[\s\S]{" + str(_HUGE_JSON_THRESHOLD) + r",\}")


# 非业务顶层容器（按 SPEC §4.1）
_NOISE_ID_PATTERNS: tuple[str, ...] = (
    "div__header",
    "timeoutblocker",
    "timeoutpopup",
)


# class 中包含以下关键字的容器也按装饰剔除。
# 注意：`ns-child-component` 用于包裹"页头/页脚/主区"等多个分区，不能整体当装饰——只针对
# `#div__header` 这种带特定 ID 的场景才剥离（见上方 `_NOISE_ID_PATTERNS`）。
_DECORATION_CLASS_HINTS: tuple[str, ...] = (
    "noprint",
    "uir-button",
)


class HTMLParser:
    """HTML → BeautifulSoup 解析器（带降噪）。

    用法:
        parser = HTMLParser()
        soup = parser.parse(Path("a.html"))
        # 后续对 soup 树做定位/抽取
    """

    def parse(self, html_path: Path) -> BeautifulSoup:
        """读取文件 + 解析 + 降噪；返回 soup 根节点（仍是 `<html>` 或最大节点）。"""
        raw = html_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(raw, "lxml")
        self._strip_noise(soup)
        return soup

    # ────────────────────────── 降噪内部 ──────────────────────────

    def _strip_noise(self, soup: BeautifulSoup) -> None:
        for tag_name in _NOISE_TAGS:
            for el in soup.find_all(tag_name):
                el.decompose()

        # 移除 `<img>`：按 SPEC §4.1 step 1.5（用户要求跳过图片）
        # 但表头/单元格内用作图标的 img 也按装饰处理（NetSuite 的 checkboximage 等）
        for el in soup.find_all("img"):
            el.decompose()

        # 移除注释
        for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
            c.extract()

        # 移除巨型 JSON 配置块 script（在其文本里检测超长 {...}）
        for el in soup.find_all("script"):
            text = el.string or el.get_text()
            if _HUGE_JSON_PATTERN.search(text or ""):
                el.decompose()

        # 移除非业务顶层容器
        for nid in _NOISE_ID_PATTERNS:
            for el in soup.find_all(id=lambda v, _nid=nid: v == _nid):
                el.decompose()

        # 移除 display:none 装饰块（含属性 style 中含 display:none 的子节点）
        self._strip_display_none(soup)

        # 移除装饰 class 容器：找到但不全删，避免误伤——只剥掉 leaf 装饰（无嵌套业务数据）
        self._strip_decoration_classes(soup)

    def _strip_display_none(self, soup: BeautifulSoup) -> None:
        """仅剥离"装饰性" display:none 节点。

        规则（防误伤）：
        - 仅 leaf 节点（不再含子标签的纯文本/inline 装饰）才被 decompose；
        - 含子标签的 display:none 容器（如未激活 NetSuite tabs）保留数据，只记录 warning。
        """
        targets: list[Tag] = []
        for el in soup.find_all(True):
            style = el.get("style") or ""
            if re.search(r"display\s*:\s*none", style, flags=re.I):
                # leaf 判定：没有子标签（允许 whitespace text nodes）
                has_tag_child = any(isinstance(c, Tag) for c in el.children)
                if not has_tag_child:
                    targets.append(el)
        for el in targets:
            if el.parent is not None:
                el.decompose()

    def _strip_decoration_classes(self, soup: BeautifulSoup) -> None:
        """移除 class 含 `noprint` / `uir-button` 的整段装饰块。

        这些块通常不携带业务数据；含 `data-nsps-id` 开头为 `field_` 的祖先链路除外（避免误伤字段）。
        """
        targets: list[Tag] = []
        for el in soup.find_all(True):
            classes = el.get("class") or []
            if not any(self._class_has_hint(c) for c in classes):
                continue
            # 保护：field 控件保留
            if el.get("data-nsps-type") == "field":
                continue
            # 保护：表格数据行保留
            class_set = set(classes)
            if el.name == "tr" and (
                any(c.startswith("uir-machine-row") for c in class_set)
                or any(c.startswith("uir-list-row") for c in class_set)
            ):
                continue
            # 保护：表单主区节点（id=div__body 等）不剥
            el_id = el.get("id") or ""
            if el_id.startswith("div__body") or el_id == "body":
                continue
            # 保护：含数据表的 ancestor 不能剥
            if el.find("table"):
                continue
            targets.append(el)
        for el in targets:
            if el.parent is not None:
                el.decompose()

    @staticmethod
    def _class_has_hint(cls: str) -> bool:
        cls_lower = cls.lower()
        return any(hint in cls_lower for hint in _DECORATION_CLASS_HINTS)
