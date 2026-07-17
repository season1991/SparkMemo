"""/api/dsp-uploads 路由（v0.5）。

错误约定（与 spec §错误约定 一一对应）：
- 400：文件名 < 3 段；version_date 非 YYYY-MM-DD；quantity 含非数字 / 非整数浮点
- 404：批次不存在
- 409：同 (vendor, item, sub_item, version_date) 已存在
- 413：文件 > 20 MB
- 415：MIME 非 .xlsx
- 422：Sheet 'DSP' 不存在
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.exc import IntegrityError

from app import crud, models
from app.deps import get_db
from app.schemas import (
    DspUploadListResponse,
    DspUploadRead,
    DspUploadRowListResponse,
    DspUploadRowRead,
)
from app.services.dsp_parser import (
    BadQuantityError,
    SheetMissingError,
    parse_excel,
    parse_filename,
)


router = APIRouter(prefix="/api/dsp-uploads", tags=["dsp-uploads"])

MAX_BYTES = 20 * 1024 * 1024  # 20 MB
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _today_str() -> str:
    return date.today().isoformat()


def _validate_yyyy_mm_dd(value: str) -> str:
    from datetime import date as _date

    try:
        _date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="version_date must be YYYY-MM-DD",
        ) from exc
    return value


def _conflict_detail(upload: models.DspUpload) -> str:
    return (
        f"version (vendor={upload.vendor}, item={upload.item}, "
        f"sub_item={upload.sub_item}, version_date={upload.version_date}) "
        f"already uploaded (upload_id={upload.id})"
    )


@router.get("", response_model=DspUploadListResponse)
def list_uploads_endpoint(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    """批次列表（按 id 倒序）。"""
    items, total = crud.dsp_upload.list_uploads(db, page=page, size=size)
    return {
        "items": [DspUploadRead.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("", response_model=DspUploadRead, status_code=201)
async def upload_endpoint(
    file: UploadFile = File(...),
    version_date: str = Form(...),
    db=Depends(get_db),
):
    """接收 multipart/form-data 上传：file + version_date。

    处理顺序：
    1. 校验 version_date 格式 → 400
    2. 校验 MIME / size → 415 / 413
    3. 读取字节流到内存 → parse_filename → parse_excel
    4. 重传冲突检测 → 409
    5. INSERT 批次元数据 → bulk INSERT 事实行
    """
    _validate_yyyy_mm_dd(version_date)

    if file.content_type != XLSX_MIME:
        raise HTTPException(status_code=415, detail="file must be .xlsx MIME type")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 20 MB limit")

    filename = file.filename or ""
    try:
        vendor, item, sub_item = parse_filename(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        fact_rows = parse_excel(content)
    except SheetMissingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BadQuantityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = crud.dsp_upload.find_by_version(
        db,
        vendor=vendor,
        item=item,
        sub_item=sub_item,
        version_date=version_date,
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=_conflict_detail(existing))

    try:
        upload = crud.dsp_upload.create_upload(
            db,
            vendor=vendor,
            item=item,
            sub_item=sub_item,
            version_date=version_date,
            source_filename=filename,
            row_count=len(fact_rows),
            created_at=_today_str(),
        )
    except IntegrityError as exc:
        # 并发场景下唯一约束兜底
        db.rollback()
        existing2 = crud.dsp_upload.find_by_version(
            db,
            vendor=vendor,
            item=item,
            sub_item=sub_item,
            version_date=version_date,
        )
        if existing2 is not None:
            raise HTTPException(status_code=409, detail=_conflict_detail(existing2)) from exc
        raise

    crud.dsp_upload.bulk_insert_rows(
        db,
        upload.id,
        [
            {
                "country": fr.country,
                "category": fr.category,
                "config_code": fr.config_code,
                "data_type": fr.data_type,
                "ttl": fr.ttl,
                "ym": fr.ym,
                "week": fr.week,
                "date": fr.date,
                "quantity": fr.quantity,
            }
            for fr in fact_rows
        ],
    )

    return DspUploadRead.model_validate(upload)


@router.get("/{upload_id}", response_model=DspUploadRead)
def get_upload_endpoint(upload_id: int, db=Depends(get_db)):
    """批次详情。"""
    upload = crud.dsp_upload.get_upload(db, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="dsp upload not found")
    return DspUploadRead.model_validate(upload)


@router.get("/{upload_id}/rows", response_model=DspUploadRowListResponse)
def list_upload_rows_endpoint(
    upload_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=1000),
    db=Depends(get_db),
):
    """批次内事实行分页（按 id 升序）。"""
    if crud.dsp_upload.get_upload(db, upload_id) is None:
        raise HTTPException(status_code=404, detail="dsp upload not found")
    items, total = crud.dsp_upload.list_rows(db, upload_id, page=page, size=size)
    return {
        "items": [DspUploadRowRead.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "size": size,
    }


@router.delete("/{upload_id}", status_code=204)
def delete_upload_endpoint(upload_id: int, db=Depends(get_db)):
    """删除批次；外键 ON DELETE CASCADE 自动清空事实行。"""
    ok = crud.dsp_upload.delete_upload(db, upload_id)
    if not ok:
        raise HTTPException(status_code=404, detail="dsp upload not found")
    return None