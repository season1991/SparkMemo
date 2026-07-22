"""/api/html-to-excel 路由（SPEC §8 / §8.x v0.2.0）。

端点（v0.1.0）：
- POST /api/html-to-excel/extract
    上传 HTML 文件 + 控件标题 → 解析并产出 xlsx → 返回下载信息。
- GET /api/html-to-excel/download/{filename}
    下载已生成的 xlsx。

端点（v0.2.0）：
- POST /api/html-to-excel/inspect
    上传 HTML 文件 → 列出所有可下载控件（带 index + preview + 行/列数）。
- POST /api/html-to-excel/extract-by-index
    按 index 直接抽控件并产出 xlsx（无需 title）。

错误约定：
- 404 title_not_found
- 409 multiple_matches（响应体含 candidates）
- 422 index_out_of_range / html_unparseable / empty_html
- 413 文件 > MAX_BYTES（默认 20 MB）
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.services.html_to_excel import HtmlToExcelPipeline


router = APIRouter(prefix="/api/html-to-excel", tags=["html-to-excel"])

MAX_BYTES = 20 * 1024 * 1024  # 20 MB
XLSX_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# 输出目录：固定到 backend/outputs/html_to_excel
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs" / "html_to_excel"
DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _save_tmp(raw: bytes, original_filename: str | None, prefix: str) -> Path:
    """保存上传文件到 `_tmp/<prefix>_<original>` 供 pipeline 解析。"""
    tmp_dir = DEFAULT_OUTPUT_DIR / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    safe_name = original_filename or "in.html"
    tmp_path = tmp_dir / f"{prefix}_{safe_name}"
    tmp_path.write_bytes(raw)
    return tmp_path


# ==================== v0.1.0 ====================


@router.post("/extract")
async def extract(
    html_file: UploadFile = File(..., description="HTML 文件（.html / .htm / .txt 等任意文本扩展名均可）"),
    title: str = Form(..., description="控件标题（中/英文）"),
    filename_hint: str | None = Form(None),
    auto_select_first: bool = Form(True, description="多匹配时是否自动选第一个"),
) -> dict:
    """解析 HTML 并生成 xlsx，返回下载信息。"""
    raw = await html_file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"上传文件超过 {MAX_BYTES // (1024 * 1024)} MB 限制")
    if not raw:
        raise HTTPException(status_code=422, detail="empty_html")

    tmp_path = _save_tmp(raw, html_file.filename, "extract")

    result = HtmlToExcelPipeline().run(
        html_path=tmp_path,
        title=title,
        output_dir=DEFAULT_OUTPUT_DIR,
        filename_hint=filename_hint,
        auto_select_first=auto_select_first,
    )

    if not result.ok:
        status_map = {
            "title_not_found": 404,
            "multiple_matches": 409,
            "html_unparseable": 422,
            "empty_html": 422,
            "index_out_of_range": 422,
        }
        raise HTTPException(
            status_code=status_map.get(result.error or "html_unparseable", 422),
            detail=result.to_dict(),
        )

    return result.to_dict()


@router.get("/download/{filename}")
def download(filename: str):
    """下载 /outputs/html_to_excel/{filename}.xlsx。"""
    safe_name = Path(filename).name
    target = DEFAULT_OUTPUT_DIR / safe_name
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="file_not_found")
    if not target.suffix.lower() == ".xlsx":
        raise HTTPException(status_code=422, detail="not_xlsx")
    return FileResponse(
        path=target,
        filename=safe_name,
        media_type=XLSX_CT,
    )


# ==================== v0.2.0 新增 ====================


@router.post("/inspect")
async def inspect(
    html_file: UploadFile = File(..., description="HTML 文件（≤20 MB）"),
) -> dict:
    """列出 HTML 中所有可下载的控件（带 index + preview + 行/列数）。

    成功响应：
    ```json
    {
      "ok": true,
      "html_size_kb": 3131,
      "controls": [
        {"index": 0, "control_type": "table", "suggested_title": "Item",
         "title_source": "thead-th", "row_count": 23, "column_count": 107,
         "preview": {"headers": ["..."], "first_rows": [["..."]]}}
      ]
    }
    ```

    `controls: []` 是合法响应（页面无显著表格时）。
    """
    raw = await html_file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"上传文件超过 {MAX_BYTES // (1024 * 1024)} MB 限制")
    if not raw:
        raise HTTPException(status_code=422, detail="empty")

    tmp_path = _save_tmp(raw, html_file.filename, "inspect")
    result = HtmlToExcelPipeline().inspect(tmp_path)

    if not result.ok:
        status_map = {"html_unparseable": 422, "empty_html": 422}
        raise HTTPException(
            status_code=status_map.get(result.error or "html_unparseable", 422),
            detail=result.to_dict(),
        )

    return result.to_dict()


@router.post("/extract-by-index")
async def extract_by_index(
    html_file: UploadFile = File(..., description="HTML 文件（≤20 MB）"),
    index: int = Form(..., description="0-based，对应上一次 /inspect 响应的 controls[i].index"),
    filename_hint: str | None = Form(None),
) -> dict:
    """按 index 抽控件 → 生成 xlsx → 返回下载信息。

    成功响应与 /extract 同 schema。
    index 越界时：422 + response.detail.candidates 列出所有 suggested_title。
    """
    raw = await html_file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"上传文件超过 {MAX_BYTES // (1024 * 1024)} MB 限制")
    if not raw:
        raise HTTPException(status_code=422, detail="empty")

    tmp_path = _save_tmp(raw, html_file.filename, "extract_by_index")
    result = HtmlToExcelPipeline().run_by_index(
        html_path=tmp_path,
        index=index,
        output_dir=DEFAULT_OUTPUT_DIR,
        filename_hint=filename_hint,
    )

    if not result.ok:
        status_map = {
            "title_not_found": 404,
            "multiple_matches": 409,
            "index_out_of_range": 422,
            "html_unparseable": 422,
            "empty_html": 422,
        }
        raise HTTPException(
            status_code=status_map.get(result.error or "html_unparseable", 422),
            detail=result.to_dict(),
        )

    return result.to_dict()
