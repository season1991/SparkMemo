# /api/email 路由：邮件发送相关接口（当前仅 send-test）
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app import crud
from app.deps import get_db
from app.schemas import EmailConfigWrite
from app.services.mailer import MailerError, send_html


router = APIRouter(prefix="/api/email", tags=["email"])


def _build_test_html(recipient_email: str) -> str:
    """构造测试邮件 HTML：固定模板，便于人工识别。"""
    sent_at = datetime.now(timezone.utc).isoformat()
    return (
        "<h3>SparkMemo 邮件连通性测试</h3>"
        "<p>这是一封来自 SparkMemo 的测试邮件。</p>"
        f"<p>发送时间：{sent_at}</p>"
        f"<p>收件人：{recipient_email}</p>"
    )


@router.post("/send-test")
def send_test_email(payload: EmailConfigWrite, db=Depends(get_db)):
    """测试发送：先自动保存入参配置（等价于 PUT /api/email-config），
    再发送一封固定模板的连通性测试邮件。

    不受 active 开关约束：纯连通性验证。
    """
    # 1. 持久化入参（写后调度器同步）
    row = crud.email_config.upsert_email_config(db, payload)

    # 2. 构造测试邮件并发送
    subject = "[SparkMemo] 邮件连通性测试"
    html = _build_test_html(row.recipient_email)
    try:
        send_html(row, subject, html)
    except MailerError as exc:
        # SMTP 失败 → 500 + 错误信息
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "ok": True,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "recipient": row.recipient_email,
    }