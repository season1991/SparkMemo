"""/api/cross-table-fill 路由（v0.6.0）。

错误约定（与 spec §错误约定 一一对应）：
- 400: data 行 cell 含不支持类型（如 datetime）
- 401: download token 缺失 / 错误 / 过期
- 404: job_id 不存在
- 409: 同 job 已 executed / 过期 / overwrite 缺 token / new_column-only 多 token / download 时 status!=executed
- 413: 任一文件 > 20 MB
- 415: 任一文件 MIME 非 .xlsx
- 422: 工作簿无 sheet / 表头为空 / 表头重复 / 主键字段不在对应 headers / mapping 字段缺失 / mode 取值非法 / keys 等长校验失败

POST /jobs 接 multipart，target_file + base_file 双文件 + 可选 expires_in_hours。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app import crud, models
from app.deps import get_db
from app.schemas import (
    CrossTableFillConfigDigest,
    CrossTableFillConfigRequest,
    CrossTableFillConfigResponse,
    CrossTableFillExecuteResponse,
    CrossTableFillExecuteSummary,
    CrossTableFillJobListResponse,
    CrossTableFillJobRead,
    CrossTableFillUploadResponse,
)
from app.services.cross_table_fill import (
    BadCellTypeError,
    DuplicateHeadersError,
    EmptyHeadersError,
    ExecuteConfig,
    MappingSpec,
    NoSheetError,
    PREVIEW_LIMIT,
    build_xlsx,
    execute_match,
    parse_table,
)


router = APIRouter(prefix="/api/cross-table-fill", tags=["cross-table-fill"])

MAX_BYTES = 20 * 1024 * 1024  # 20 MB；spec §POST 入参硬上限
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _job_to_read(job: models.CrossTableFillJob) -> CrossTableFillJobRead:
    """ORM 行 → Pydantic read schema；反序列化 JSON headers。"""
    return CrossTableFillJobRead(
        id=job.id,
        target_filename=job.target_filename,
        base_filename=job.base_filename,
        target_headers=json.loads(job.target_headers),
        base_headers=json.loads(job.base_headers),
        target_row_count=job.target_row_count,
        base_row_count=job.base_row_count,
        status=job.status,
        result_row_count=job.result_row_count,
        filled_count=job.filled_count,
        unmatched_count=job.unmatched_count,
        multi_match_count=job.multi_match_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
        expires_at=job.expires_at,
    )


def _upload_response(job: models.CrossTableFillJob) -> CrossTableFillUploadResponse:
    """upload 阶段：构造 CrossTableFillUploadResponse。"""
    return CrossTableFillUploadResponse(
        job_id=job.id,
        target_filename=job.target_filename,
        base_filename=job.base_filename,
        target_headers=json.loads(job.target_headers),
        base_headers=json.loads(job.base_headers),
        target_row_count=job.target_row_count,
        base_row_count=job.base_row_count,
        status=job.status,
        expires_at=job.expires_at,
    )


async def _read_xlsx_or_error(file: UploadFile, role: str) -> tuple[list[str], list[dict]]:
    """读取并解析一个上传的 xlsx 文件；统一抛 4xx。"""
    if file.content_type != XLSX_MIME:
        raise HTTPException(
            status_code=422,
            detail=f"{role}_file must be .xlsx MIME type",
        )
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"{role}_file exceeds {MAX_BYTES // (1024 * 1024)} MB limit",
        )
    try:
        headers, rows = parse_table(content, role)
    except NoSheetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EmptyHeadersError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DuplicateHeadersError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BadCellTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # openpyxl raise 等底层错误 → 400
        raise HTTPException(status_code=400, detail=f"failed to parse {role}_file: {exc}") from exc
    return headers, rows


# ====================== 端点 ======================


@router.post("/jobs", response_model=CrossTableFillUploadResponse, status_code=201)
async def create_job_endpoint(
    target_file: UploadFile = File(...),
    base_file: UploadFile = File(...),
    expires_in_hours: Optional[int] = Form(default=None),
    db=Depends(get_db),
):
    """上传 + 解析两张表（multipart），返回 job_id 与 headers + 行数。

    参数:
        target_file: 目标表 xlsx；MIME 必须 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`。
        base_file: 基础表 xlsx；同上。
        expires_in_hours: 过期小时数（1-168；默认 24）。
        db: FastAPI 注入的 Session。

    返回:
        CrossTableFillUploadResponse: 含 job_id / headers / row_count / status / expires_at。

    异常:
        413: 任一文件 > 20 MB。
        422: 任一文件 MIME 不符 / 工作簿无 sheet / 表头为空 / 表头重复。
        400: 任一文件 cell 含不支持类型。
    """
    if expires_in_hours is not None:
        if not (1 <= expires_in_hours <= 168):
            raise HTTPException(
                status_code=422,
                detail="expires_in_hours must be in [1, 168]",
            )
    else:
        expires_in_hours = 24

    target_headers, target_rows = await _read_xlsx_or_error(target_file, "target")
    base_headers, base_rows = await _read_xlsx_or_error(base_file, "base")

    job = crud.cross_table_fill.create_job(
        db,
        target_filename=target_file.filename or "target.xlsx",
        base_filename=base_file.filename or "base.xlsx",
        target_headers=target_headers,
        base_headers=base_headers,
        target_row_count=len(target_rows),
        base_row_count=len(base_rows),
        expires_in_hours=expires_in_hours,
    )
    crud.cross_table_fill.bulk_insert_rows(
        db, job_id=job.id, role="target", rows=target_rows,
    )
    crud.cross_table_fill.bulk_insert_rows(
        db, job_id=job.id, role="base", rows=base_rows,
    )
    return _upload_response(job)


@router.get("/jobs/{job_id}", response_model=CrossTableFillJobRead)
def get_job_endpoint(job_id: int, db=Depends(get_db)):
    """单查 job 元数据。

    参数:
        job_id: 任务主键。
        db: FastAPI 注入的 Session。

    返回:
        CrossTableFillJobRead: 单个 job 的元数据 + 状态与执行摘要。

    异常:
        404: job_id 不存在。
    """
    job = crud.cross_table_fill.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="cross_table_fill job not found")
    return _job_to_read(job)


@router.get("/jobs", response_model=CrossTableFillJobListResponse)
def list_jobs_endpoint(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """job 列表（按 id 倒序），可选 status 过滤。"""
    items, total = crud.cross_table_fill.list_jobs(
        db, page=page, size=size, status=status,
    )
    return CrossTableFillJobListResponse(
        items=[_job_to_read(j) for j in items],
        total=total,
        page=page,
        size=size,
    )


def _validate_config(
    payload: CrossTableFillConfigRequest,
    target_headers: list[str],
    base_headers: list[str],
) -> list[str]:
    """配置校验：返回 warnings 列表（warnings 不阻断，仅提示）。

    抛出 HTTPException(422) 当字段缺失或非法。
    """
    warnings: list[str] = []
    target_set = set(target_headers)
    base_set = set(base_headers)

    # target_keys 校验
    for k in payload.target_keys:
        if k not in target_set:
            raise HTTPException(
                status_code=422,
                detail=f"target_keys contains unknown field: '{k}'",
            )
    # base_keys 校验
    for k in payload.base_keys:
        if k not in base_set:
            raise HTTPException(
                status_code=422,
                detail=f"base_keys contains unknown field: '{k}'",
            )
    # keys 等长（已被 Pydantic model_validator 校验；这里再保险一遍）
    if len(payload.target_keys) != len(payload.base_keys):
        raise HTTPException(
            status_code=422,
            detail="target_keys and base_keys must have equal length",
        )
    # mappings 字段校验（v0.6.0.1.0：按 mode 分支校验 target_field）
    for m in payload.mappings:
        if m.base_field not in base_set:
            raise HTTPException(
                status_code=422,
                detail=f"mappings.base_field '{m.base_field}' not in base_headers",
            )
        if m.mode == "overwrite":
            # overwrite 模式：target_field 必须严格指向 target 已有列
            if m.target_field not in target_set:
                raise HTTPException(
                    status_code=422,
                    detail=f"mappings.target_field '{m.target_field}' not in target_headers (mode='overwrite' requires existing column)",
                )
        else:
            # new_column 模式：target_field 是用户自由输入的新列名，不要求在 target_headers 中；
            # 与 target_headers 同名的情况由 execute 阶段加 _filled 后缀处理（warnings 提示用户）。
            # 此处仅校验非空。
            if not m.target_field or not str(m.target_field).strip():
                raise HTTPException(
                    status_code=422,
                    detail="mappings.target_field must be a non-empty string (mode='new_column')",
                )

    # warnings：target 表空键值行（此处不展开整表，仅基于已知 rows 估算）
    # 由于 warnings 在路由层生成，需 query DB → 留给调用方
    return warnings


@router.patch("/jobs/{job_id}/config", response_model=CrossTableFillConfigResponse)
def patch_config_endpoint(
    job_id: int,
    payload: CrossTableFillConfigRequest,
    db=Depends(get_db),
):
    """提交主键 + 映射配置。

    参数:
        job_id: job 主键。
        payload: 配置请求体（含 join_mode / match_mode / case_sensitive / trim_strings / confirm_token）。
        db: FastAPI 注入的 Session。

    返回:
        CrossTableFillConfigResponse: 含 config_digest + warnings。

    异常:
        404: job_id 不存在。
        409: job 已 executed / 过期；overwrite 缺 token；全 new_column 多 token。
        422: 字段缺失 / mode 取值非法 / keys 不等长（由 Pydantic 拦截）。
    """
    job = crud.cross_table_fill.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="cross_table_fill job not found")

    if crud.cross_table_fill.is_job_expired(job):
        raise HTTPException(
            status_code=409,
            detail=f"job expired (expires_at={job.expires_at})",
        )

    if job.status == "executed":
        raise HTTPException(
            status_code=409,
            detail="job already executed; reconfiguration is not allowed",
        )

    target_headers = json.loads(job.target_headers)
    base_headers = json.loads(job.base_headers)

    # 模型层二次校验（即便 model_validator 已挡，这里给出 spec-aligned 的 422 detail）
    _validate_config(payload, target_headers, base_headers)

    warnings: list[str] = []
    has_overwrite = any(m.mode == "overwrite" for m in payload.mappings)
    has_new_column = any(m.mode == "new_column" for m in payload.mappings)

    if has_overwrite and not payload.confirm_token:
        raise HTTPException(
            status_code=409,
            detail="confirm_token is required when any mapping mode is 'overwrite'",
        )
    if not has_overwrite and payload.confirm_token is not None:
        raise HTTPException(
            status_code=409,
            detail="confirm_token must be null when no mapping uses 'overwrite'",
        )

    # warnings: target_keys 在 target 表是否有空键值行
    target_rows = crud.cross_table_fill.get_rows_by_role(
        db, job_id=job_id, role="target",
    )
    empty_key_count = sum(
        1 for r in target_rows
        if any(r.get(k) in (None, "") for k in payload.target_keys)
    )
    if empty_key_count > 0:
        warnings.append(
            f"target_keys 在 target 表有 {empty_key_count} 个空键值行，运行时将判为 unmatched"
        )
    # warnings: mappings 中 new_column 触发 _filled 重命名的字段
    existing = set(target_headers)
    for m in payload.mappings:
        if m.mode == "new_column" and m.target_field in existing:
            warnings.append(
                f"字段 '{m.target_field}' 与 target 已有列同名，将自动加 _filled 后缀"
            )

    # 写入 configs
    mappings_dict = [m.model_dump() for m in payload.mappings]
    config = crud.cross_table_fill.upsert_config(
        db,
        job_id=job_id,
        target_keys=payload.target_keys,
        base_keys=payload.base_keys,
        mappings=mappings_dict,
        join_mode=payload.join_mode,
        match_mode=payload.match_mode,
        case_sensitive=payload.case_sensitive,
        trim_strings=payload.trim_strings,
        confirm_token=payload.confirm_token,
    )

    # job.status → configured
    crud.cross_table_fill.update_job_status(db, job, status="configured")

    digest = CrossTableFillConfigDigest(
        target_keys=payload.target_keys,
        base_keys=payload.base_keys,
        mapping_count=len(payload.mappings),
        has_overwrite=has_overwrite,
        has_new_column=has_new_column,
        join_mode=payload.join_mode,
        match_mode=payload.match_mode,
        case_sensitive=payload.case_sensitive,
        trim_strings=payload.trim_strings,
    )
    return CrossTableFillConfigResponse(
        job_id=job_id,
        status="configured",
        config_digest=digest,
        warnings=warnings,
    )


@router.post("/jobs/{job_id}/execute", response_model=CrossTableFillExecuteResponse)
def execute_job_endpoint(job_id: int, db=Depends(get_db)):
    """执行匹配，返回前 1000 行预览 + download_token（5 min TTL）。"""
    job = crud.cross_table_fill.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="cross_table_fill job not found")

    if crud.cross_table_fill.is_job_expired(job):
        raise HTTPException(
            status_code=409,
            detail=f"job expired (expires_at={job.expires_at})",
        )

    config = crud.cross_table_fill.get_config(db, job_id)
    if config is None:
        raise HTTPException(
            status_code=409,
            detail="job has no config; PATCH /config first",
        )

    target_headers = json.loads(job.target_headers)
    base_headers = json.loads(job.base_headers)
    target_rows = crud.cross_table_fill.get_rows_by_role(
        db, job_id=job_id, role="target",
    )
    base_rows = crud.cross_table_fill.get_rows_by_role(
        db, job_id=job_id, role="base",
    )

    mappings = [
        MappingSpec(base_field=m["base_field"], target_field=m["target_field"], mode=m["mode"])
        for m in json.loads(config.mappings)
    ]
    cfg = ExecuteConfig(
        target_keys=json.loads(config.target_keys),
        base_keys=json.loads(config.base_keys),
        mappings=mappings,
        join_mode=config.join_mode,
        match_mode=config.match_mode,
        case_sensitive=config.case_sensitive,
        trim_strings=config.trim_strings,
    )

    try:
        result = execute_match(
            target_headers=target_headers,
            target_rows=target_rows,
            base_headers=base_headers,
            base_rows=base_rows,
            cfg=cfg,
        )
    except Exception as exc:
        crud.cross_table_fill.update_job_status(db, job, status="failed")
        raise HTTPException(status_code=400, detail=f"execute_match failed: {exc}") from exc

    crud.cross_table_fill.update_job_status(
        db, job,
        status="executed",
        result_row_count=result.result_row_count,
        filled_count=result.filled_count,
        unmatched_count=result.unmatched_count,
        multi_match_count=result.multi_match_count,
    )

    # preview 取前 1000 行
    preview_dicts: list[dict] = []
    for row_values in result.final_rows[:PREVIEW_LIMIT]:
        d = {}
        for h, v in zip(result.final_headers, row_values):
            d[h] = v
        preview_dicts.append(d)

    token = crud.cross_table_fill.put_download_token(job_id)
    return CrossTableFillExecuteResponse(
        job_id=job_id,
        status="executed",
        summary=CrossTableFillExecuteSummary(
            target_row_count=job.target_row_count,
            result_row_count=result.result_row_count,
            filled_count=result.filled_count,
            unmatched_count=result.unmatched_count,
            multi_match_count=result.multi_match_count,
        ),
        preview_headers=result.final_headers,
        preview=preview_dicts,
        download_token=token,
        download_url=f"/api/cross-table-fill/jobs/{job_id}/download?token={token}",
    )


def _download_filename(job_id: int) -> str:
    """生成形如 cross_table_fill_12_filled_20260723143000.xlsx 的文件名。"""
    return f"cross_table_fill_{job_id}_filled_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"


@router.get("/jobs/{job_id}/download")
def download_job_endpoint(
    job_id: int,
    token: Optional[str] = Query(default=None),
    db=Depends(get_db),
):
    """下载执行结果 xlsx；需 5 min 内有效的 token。

    返回:
        StreamingResponse: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
        二进制流 + `Content-Disposition: attachment; filename="..."`。

    异常:
        401: token 缺失 / 错误 / 过期。
        404: job 不存在。
        409: job.status != 'executed'（即便 token 合法）。
    """
    if not token:
        raise HTTPException(status_code=401, detail="missing download token")

    job = crud.cross_table_fill.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="cross_table_fill job not found")

    if job.status != "executed":
        raise HTTPException(
            status_code=409,
            detail=f"job status is '{job.status}', download requires 'executed'",
        )

    job_id_from_token = crud.cross_table_fill.take_download_token(token)
    if job_id_from_token is None or job_id_from_token != job_id:
        raise HTTPException(status_code=401, detail="invalid or expired download token")

    # 重算 xlsx（与 execute 中算法一致）
    config = crud.cross_table_fill.get_config(db, job_id)
    target_headers = json.loads(job.target_headers)
    base_headers = json.loads(job.base_headers)
    target_rows = crud.cross_table_fill.get_rows_by_role(
        db, job_id=job_id, role="target",
    )
    base_rows = crud.cross_table_fill.get_rows_by_role(
        db, job_id=job_id, role="base",
    )
    mappings = [
        MappingSpec(base_field=m["base_field"], target_field=m["target_field"], mode=m["mode"])
        for m in json.loads(config.mappings)
    ]
    cfg = ExecuteConfig(
        target_keys=json.loads(config.target_keys),
        base_keys=json.loads(config.base_keys),
        mappings=mappings,
        join_mode=config.join_mode,
        match_mode=config.match_mode,
        case_sensitive=config.case_sensitive,
        trim_strings=config.trim_strings,
    )
    result = execute_match(
        target_headers=target_headers,
        target_rows=target_rows,
        base_headers=base_headers,
        base_rows=base_rows,
        cfg=cfg,
    )
    content = build_xlsx(result.final_headers, result.final_rows)
    filename = _download_filename(job_id)
    return StreamingResponse(
        iter([content]),
        media_type=XLSX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job_endpoint(job_id: int, db=Depends(get_db)):
    """主动清理 job（级联清 rows / configs）。"""
    ok = crud.cross_table_fill.delete_job(db, job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="cross_table_fill job not found")
    return None
