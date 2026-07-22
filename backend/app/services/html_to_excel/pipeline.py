"""流水线总编排（SPEC §4 5/6 阶段 + §5.x 用户决策）。

对外入口：
- `HtmlToExcelPipeline.run(...)`           v0.1.0：按 title 抽
- `HtmlToExcelPipeline.inspect(...)`       v0.2.0：列出所有控件
- `HtmlToExcelPipeline.run_by_index(...)`  v0.2.0：按 index 抽
"""
from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from .inspector import HTMLInspector
from .locator import TitleLocator, select_first
from .parser import HTMLParser
from .recognizers import find_control_root
from .schemas import InspectionResult, ExtractionResult
from .writer import ExcelWriter, default_filename


class HtmlToExcelPipeline:
    """5 阶段流水线：

    1. 解析 + 降噪（HTMLParser）
    2. 标题定位（TitleLocator） / 枚举（HTMLInspector）
    3. 控件范围识别（find_control_root + Recognizer）
    4. 内容抽取（recognizer.extract）
    5. JSON → xlsx（ExcelWriter）
    """

    def __init__(self) -> None:
        self.parser = HTMLParser()
        self.locator = TitleLocator()
        self.inspector = HTMLInspector()
        self.writer = ExcelWriter()

    # ────────────────────────── v0.1.0：按 title ──────────────────────────

    def run(
        self,
        html_path: str | Path,
        title: str,
        output_dir: str | Path,
        filename_hint: str | None = None,
        auto_select_first: bool = True,
    ) -> ExtractionResult:
        soup, err = self._parse_safe(html_path)
        if err is not None:
            return err

        # 2) 标题定位
        candidates, suggestions = self.locator.find(soup, title)
        if not candidates:
            return ExtractionResult(
                ok=False,
                error="title_not_found",
                message=f"未找到标题为 `{title}` 的控件",
                candidates=suggestions or None,
            )

        if len(candidates) > 1 and not auto_select_first:
            return ExtractionResult(
                ok=False,
                error="multiple_matches",
                message=f"找到 {len(candidates)} 个同名控件，请提供选择",
                candidates=[c.matched_text for c in candidates],
            )

        chosen = select_first(candidates)
        if chosen is None:
            return ExtractionResult(ok=False, error="title_not_found", message="无可用候选")

        return self._run_with_candidate(chosen, soup, output_dir, filename_hint)

    # ────────────────────────── v0.2.0：inspect ──────────────────────────

    def inspect(self, html_path: str | Path) -> InspectionResult:
        """列出 HTML 中所有可下载控件（带 row/col/preview）。"""
        raw_bytes = Path(html_path).read_bytes() if Path(html_path).exists() else b""
        soup, err = self._parse_safe(html_path)
        if err is not None:
            return InspectionResult(ok=False, error=err.error, message=err.message, html_size=len(raw_bytes))

        detected = self.inspector.inspect(soup)
        return InspectionResult(
            ok=True,
            html_size=len(raw_bytes),
            controls=[d.summary for d in detected],
        )

    # ────────────────────────── v0.2.0：run_by_index ──────────────────────────

    def run_by_index(
        self,
        html_path: str | Path,
        index: int,
        output_dir: str | Path,
        filename_hint: str | None = None,
    ) -> ExtractionResult:
        """按 inspect 阶段给出的 index 抽取。"""
        if index < 0:
            return ExtractionResult(
                ok=False,
                error="index_out_of_range",
                message=f"index 必须 >= 0，实际 {index}",
            )

        soup, err = self._parse_safe(html_path)
        if err is not None:
            return err

        detected = self.inspector.inspect(soup)
        if not detected:
            return ExtractionResult(
                ok=False,
                error="empty_html",
                message="未发现可下载的显著控件",
                candidates=[],
            )
        if index >= len(detected):
            return ExtractionResult(
                ok=False,
                error="index_out_of_range",
                message=f"index {index} 越界；HTML 中共有 {len(detected)} 个控件（0..{len(detected) - 1}）",
                candidates=[d.summary.suggested_title for d in detected],
            )

        target = detected[index]
        # 复用 inspect 时已经做好的完整 ExtractedControl（节省 1 次 extract）
        control = target.control
        # 用 suggested_title 重写 matched_text 与控制标识，让输出文件名 / matched_title
        # 看起来更像是来自"按标题抽取"而不是默认的 `table`
        control.title = target.summary.suggested_title or control.control_type
        control.matched_text = target.summary.suggested_title
        control.source = target.summary.title_source

        output_dir = Path(output_dir)
        matched_label = target.summary.suggested_title or f"control_{index}"
        filename = default_filename(matched_title=matched_label, hint=filename_hint)
        xlsx_path = output_dir / filename
        try:
            self.writer.write(control, xlsx_path)
        except Exception as exc:  # noqa: BLE001
            return ExtractionResult(ok=False, error="html_unparseable", message=f"写入失败: {exc!s}")

        return ExtractionResult(
            ok=True,
            control_type=control.control_type,
            matched_title=matched_label,
            xlsx_path=str(xlsx_path),
            download_filename=filename,
            rows=control.row_count,
            columns=control.column_count,
            warnings=list(control.warnings),
        )

    # ────────────────────────── 内部辅助 ──────────────────────────

    def _parse_safe(self, html_path: str | Path) -> tuple[BeautifulSoup | None, ExtractionResult | None]:
        """返回 (soup, None) 或 (None, error_result)。"""
        html_path = Path(html_path)
        if not html_path.exists() or not html_path.is_file():
            return None, ExtractionResult(ok=False, error="html_unparseable", message=f"文件不存在: {html_path}")
        try:
            soup = self.parser.parse(html_path)
        except Exception as exc:  # noqa: BLE001
            return None, ExtractionResult(ok=False, error="html_unparseable", message=f"解析失败: {exc!s}")
        if soup is None or len(soup.find_all(True)) == 0:
            return None, ExtractionResult(ok=False, error="empty_html", message="降噪后无业务节点")
        return soup, None

    def _run_with_candidate(
        self,
        chosen,
        soup: BeautifulSoup,
        output_dir: str | Path,
        filename_hint: str | None,
    ) -> ExtractionResult:
        """run() 与 run_by_index() 共享的"识别+抽取+写 xlsx" 路径。"""
        rec, root_node = find_control_root(chosen.node, soup=soup)
        if rec is None or root_node is None:
            return ExtractionResult(
                ok=False,
                error="html_unparseable",
                message="无法识别控件类型（既不是 table/div-grid/field-group/list）",
            )
        try:
            control = rec.extract(root_node, chosen)
        except Exception as exc:  # noqa: BLE001
            return ExtractionResult(ok=False, error="html_unparseable", message=f"抽取失败: {exc!s}")

        output_dir = Path(output_dir)
        filename = default_filename(matched_title=chosen.matched_text, hint=filename_hint)
        xlsx_path = output_dir / filename
        try:
            self.writer.write(control, xlsx_path)
        except Exception as exc:  # noqa: BLE001
            return ExtractionResult(ok=False, error="html_unparseable", message=f"写入失败: {exc!s}")

        return ExtractionResult(
            ok=True,
            control_type=control.control_type,
            matched_title=chosen.matched_text,
            xlsx_path=str(xlsx_path),
            download_filename=filename,
            rows=control.row_count,
            columns=control.column_count,
            warnings=list(control.warnings),
        )


def run_sync(
    html_path: str | Path,
    title: str,
    output_dir: str | Path,
    filename_hint: str | None = None,
) -> ExtractionResult:
    """便捷同步入口（CLI/单测使用）。"""
    return HtmlToExcelPipeline().run(
        html_path=html_path,
        title=title,
        output_dir=output_dir,
        filename_hint=filename_hint,
    )
