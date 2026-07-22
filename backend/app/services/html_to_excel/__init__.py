"""HTML → Excel 模块的对外暴露。

调用示例（同步，按 title）：
    from app.services.html_to_excel import HtmlToExcelPipeline
    result = HtmlToExcelPipeline().run(html_path, "Items", Path("outputs/html_to_excel"))

调用示例（v0.2.0 列表 + 按索引下载）：
    inspection = HtmlToExcelPipeline().inspect(html_path)
    for ctrl in inspection.controls:
        print(ctrl.index, ctrl.suggested_title, ctrl.row_count, 'rows')
    result = HtmlToExcelPipeline().run_by_index(html_path, 0, Path("outputs/html_to_excel"))

CLI/同步入口：
    from app.services.html_to_excel import run_sync
    result = run_sync(html_path, "Items", Path("outputs/html_to_excel"))
"""
from .pipeline import HtmlToExcelPipeline, run_sync
from .schemas import (
    ControlPreview,
    ControlSummary,
    DetectedControl,
    ExtractionResult,
    InspectionResult,
    MatchCandidate,
)

__all__ = [
    "HtmlToExcelPipeline",
    "run_sync",
    "ExtractionResult",
    "InspectionResult",
    "ControlSummary",
    "ControlPreview",
    "DetectedControl",
    "MatchCandidate",
]
