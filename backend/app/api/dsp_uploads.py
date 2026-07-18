"""/api/dsp-uploads 路由（v0.5 → v0.5.1）。

错误约定（与 spec §错误约定 一一对应）：
- 400：version_date 非 YYYY-MM-DD；quantity 含非数字 / 非整数浮点
- 404：批次不存在
- 409：同 (vendor, item, sub_item, version_date) 已存在
- 413：文件 > 20 MB
- 415：MIME 非 .xlsx
- 422：Sheet 'DSP' 不存在；任一必填 Form 字段缺失；Excel 行 1 缺失关键列（country/category/config_code/data_type/ttl 中任一）

v0.5.1 变更：POST /api/dsp-uploads 升级为接收 4 个**必填** Form 字段（vendor / item /
sub_item / version_date）；不再调用 `parse_filename` 从文件名回退解析——文件名解析
逻辑迁至前端。本路由不再 import `parse_filename`，仅保留调用以 `parse_excel` 为核心
的解析路径。

v0.5.3 变更：新增对 `BadHeaderError` 的捕获（行 1 关键列缺失）→ 422。
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
    BadHeaderError,
    BadQuantityError,
    SheetMissingError,
    parse_excel,
)


router = APIRouter(prefix="/api/dsp-uploads", tags=["dsp-uploads"])

MAX_BYTES = 20 * 1024 * 1024  # 20 MB；spec §Post 入参硬上限
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ==================== v0.5.4 级联下拉查询（去重值） ====================


@router.get("/vendors", response_model=list[str])
def get_vendors_endpoint(db=Depends(get_db)):
    """返回所有去重的 vendor 值（按字母升序），供查询/删除页下拉使用。

    返回:
        list[str]: 去重后的 vendor 列表。

    异常:
        无业务异常。
    """
    return crud.dsp_upload.distinct_vendors(db)


@router.get("/items", response_model=list[str])
def get_items_endpoint(
    vendor: str = Query(..., description="供应商（必填，精确匹配）"),
    db=Depends(get_db),
):
    """返回指定 vendor 下所有去重的 item 值（按字母升序）。

    参数:
        vendor: 供应商；必填。
        db: FastAPI 注入的数据库 Session。

    返回:
        list[str]: 去重后的 item 列表。

    异常:
        无业务异常。
    """
    return crud.dsp_upload.distinct_items(db, vendor)


@router.get("/sub-items", response_model=list[str])
def get_sub_items_endpoint(
    vendor: str = Query(..., description="供应商（必填）"),
    item: str = Query(..., description="业务项（必填）"),
    db=Depends(get_db),
):
    """返回指定 vendor + item 下所有去重的 sub_item 值（按字母升序）。

    参数:
        vendor: 供应商；必填。
        item: 业务项；必填。
        db: FastAPI 注入的数据库 Session。

    返回:
        list[str]: 去重后的 sub_item 列表。

    异常:
        无业务异常。
    """
    return crud.dsp_upload.distinct_sub_items(db, vendor, item)


@router.get("/version-dates", response_model=list[str])
def get_version_dates_endpoint(
    vendor: str = Query(..., description="供应商（必填）"),
    item: str = Query(..., description="业务项（必填）"),
    sub_item: str = Query(..., description="子业务项（必填）"),
    db=Depends(get_db),
):
    """返回指定 vendor + item + sub_item 下所有去重的 version_date 值（按日期降序）。

    参数:
        vendor: 供应商；必填。
        item: 业务项；必填。
        sub_item: 子业务项；必填。
        db: FastAPI 注入的数据库 Session。

    返回:
        list[str]: 去重后的 version_date 列表（YYYY-MM-DD 格式，最新日期排在前面）。

    异常:
        无业务异常。
    """
    return crud.dsp_upload.distinct_version_dates(db, vendor, item, sub_item)


# ==================== 既有端点 ====================


def _today_str() -> str:
    """返回当前日期的 10 字符 YYYY-MM-DD 字符串（spec 要求 created_at 由 Python 写入，不依赖 DB 函数）。"""
    return date.today().isoformat()


def _validate_yyyy_mm_dd(value: str) -> str:
    """校验字符串是否符合 YYYY-MM-DD；不符时抛 400。

    参数:
        value: 表单字段 version_date 的原始值。

    返回:
        str: 原值（已校验）。

    异常:
        HTTPException 400: 当 value 不是合法 YYYY-MM-DD 时。
    """
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
    """生成 409 响应的 detail 字段值，包含具体冲突维度与已存在批次的 upload_id。

    参数:
        upload: 数据库中已存在的冲突批次行。

    返回:
        str: 形如 `"version (vendor=A, item=B, sub_item=C, version_date=YYYY-MM-DD) already uploaded (upload_id=N)"` 的可读描述。
    """
    return (
        f"version (vendor={upload.vendor}, item={upload.item}, "
        f"sub_item={upload.sub_item}, version_date={upload.version_date}) "
        f"already uploaded (upload_id={upload.id})"
    )


@router.get("", response_model=DspUploadListResponse)
def list_uploads_endpoint(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    vendor: str | None = Query(None),
    item: str | None = Query(None),
    sub_item: str | None = Query(None),
    version_date: str | None = Query(None),
    db=Depends(get_db),
):
    """批次列表（按 id 倒序），v0.5.4 起支持 4 个可选 filter 参数。

    参数:
        page: 页码（从 1 开始，默认 1）。
        size: 每页条数（1-100，默认 20）。
        vendor: 可选过滤；相等匹配；与 item/sub_item/version_date 组合为 AND。
        item: 可选过滤。
        sub_item: 可选过滤。
        version_date: 可选过滤；`YYYY-MM-DD` 10 字符字符串；相等匹配。
        db: FastAPI 注入的数据库 Session。

    返回:
        DspUploadListResponse: 含 `items`（批次列表）、`total`、`page`、`size` 的分页信封。

    异常:
        无业务异常。SQLAlchemy 出错时由 FastAPI 兜底为 500。
    """
    items, total = crud.dsp_upload.list_uploads(
        db,
        page=page,
        size=size,
        vendor=vendor,
        item=item,
        sub_item=sub_item,
        version_date=version_date,
    )
    return {
        "items": [DspUploadRead.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("", response_model=DspUploadRead, status_code=201)
async def upload_endpoint(
    file: UploadFile = File(...),
    vendor: str = Form(...),
    item: str = Form(...),
    sub_item: str = Form(...),
    version_date: str = Form(...),
    db=Depends(get_db),
):
    """接收 multipart/form-data 上传：file + 4 个业务字段。

    业务字段约定（v0.5.1 升级）：
    - `vendor / item / sub_item` 由前端解析文件名后填写、并允许用户在 UI 内修改后再 POST；
    - 后端**不再**从 `file.filename` 回退解析——这意味着 v0.5 引入的 `parse_filename` 函数降级为冗余 / 备用工具，仅供脚本或命令行调试使用；
    - 缺这 4 个字段中任一项 → 由 FastAPI 自动 422。

    处理顺序：
    1. 校验 version_date 格式 → 400（缺字段由 FastAPI 在更早阶段 422）
    2. 校验 MIME / size → 415 / 413
    3. 读取字节流到内存 → parse_excel
    4. 重传冲突检测 → 409
    5. INSERT 批次元数据 → bulk INSERT 事实行

    参数:
        file: 浏览器上传的 `.xlsx` 文件；MIME 必须为 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`。
        vendor: 供应商；1-64 字符；由前端解析/编辑后传入。
        item: 业务项；1-128 字符；由前端解析/编辑后传入。
        sub_item: 子业务项；1-128 字符；由前端解析/编辑后传入。
        version_date: 用户输入的批次版本日期，10 字符 `YYYY-MM-DD`。
        db: FastAPI 注入的数据库 Session。

    返回:
        DspUploadRead: 新建批次的元数据响应（含 vendor / item / sub_item / version_date / row_count / created_at）。

    异常:
        HTTPException 400: version_date 非法 / quantity 非数字或非整数浮点。
        HTTPException 413: 文件 > 20 MB。
        HTTPException 415: MIME 不是 .xlsx。
        HTTPException 422: Sheet `DSP` 不存在；任一必填 Form 字段缺失；Excel 行 1 缺失关键列（country/category/config_code/data_type/ttl 中任一列）。
        HTTPException 409: 同 (vendor, item, sub_item, version_date) 已存在；detail 含现有 upload_id。
    """
    _validate_yyyy_mm_dd(version_date)

    if file.content_type != XLSX_MIME:
        raise HTTPException(status_code=415, detail="file must be .xlsx MIME type")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 20 MB limit")

    filename = file.filename or ""

    try:
        fact_rows = parse_excel(content)
    except SheetMissingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BadHeaderError as exc:
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
        # 并发场景下唯一约束兜底：另一个请求刚插入同一版本，本请求拿到冲突后回滚并复检
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
    """批次详情。

    参数:
        upload_id: 批次主键。
        db: FastAPI 注入的数据库 Session。

    返回:
        DspUploadRead: 单个批次的元数据。

    异常:
        HTTPException 404: 批次不存在。
    """
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
    """批次内事实行分页（按 id 升序）。

    参数:
        upload_id: 批次主键。
        page: 页码（从 1 开始，默认 1）。
        size: 每页条数（1-1000，默认 100）。
        db: FastAPI 注入的数据库 Session。

    返回:
        DspUploadRowListResponse: 含 `items`（事实行列表）、`total`、`page`、`size` 的分页信封。

    异常:
        HTTPException 404: 批次不存在。
    """
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
    """删除批次；外键 ON DELETE CASCADE 自动清空事实行。

    参数:
        upload_id: 批次主键。
        db: FastAPI 注入的数据库 Session。

    返回:
        None: HTTP 204 No Content。

    异常:
        HTTPException 404: 批次不存在。
    """
    ok = crud.dsp_upload.delete_upload(db, upload_id)
    if not ok:
        raise HTTPException(status_code=404, detail="dsp upload not found")
    return None
