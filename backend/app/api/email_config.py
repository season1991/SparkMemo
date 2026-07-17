# /api/email-config 路由：邮箱配置单行 CRUD
from fastapi import APIRouter, Depends

from app import crud
from app.deps import get_db
from app.schemas import EmailConfigRead, EmailConfigWrite


router = APIRouter(prefix="/api/email-config", tags=["email-config"])


def _to_read(row) -> EmailConfigRead:
    """ORM 行 -> 响应 schema。密码不回明文，用 smtp_password_set 替代。"""
    return EmailConfigRead(
        exists=True,
        id=row.id,
        smtp_host=row.smtp_host,
        smtp_port=row.smtp_port,
        smtp_user=row.smtp_user,
        smtp_password_set=bool(row.smtp_password),
        use_tls=row.use_tls,
        sender_email=row.sender_email,
        sender_name=row.sender_name,
        recipient_email=row.recipient_email,
        recipient_name=row.recipient_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


_EMPTY_READ = EmailConfigRead(exists=False)


@router.get("", response_model=EmailConfigRead)
def get_email_config_endpoint(db=Depends(get_db)) -> EmailConfigRead:
    """取当前邮箱配置；未配置返回 exists=false + 所有字段 null/false。"""
    row = crud.email_config.get_email_config(db)
    if row is None:
        return _EMPTY_READ
    return _to_read(row)


@router.put("", response_model=EmailConfigRead)
def upsert_email_config_endpoint(
    payload: EmailConfigWrite, db=Depends(get_db)
) -> EmailConfigRead:
    """upsert 单行配置。

    - smtp_password 留空字符串或 None 视为「保留旧值」；
    - 字段校验失败由 app 级 RequestValidationError 处理器映射为 400（见 main.py）。
    """
    row = crud.email_config.upsert_email_config(db, payload)
    return _to_read(row)