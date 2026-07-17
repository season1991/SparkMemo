# 每日邮件渲染：v0.4 占位实现——等业务提醒模板确定后再展开。
from __future__ import annotations


def render_daily_dispatch(today: str, db) -> tuple[str, str]:
    """渲染每日提醒邮件的 (subject, html)。

    v0.4 占位：返回一行明确标注「提醒模板即将上线」的内容，
    避免发送完整但不正确的业务模板。

    参数:
        today: YYYY-MM-DD；由调用方（scheduler）通过 services.scheduler.get_today() 传入，
               **不**在 SQL 中调用 CURDATE() / NOW()。
        db: 当前 SQLAlchemy Session；占位版本不使用，仅为未来扩展预留接口。

    返回:
        (subject, html_body)
    """
    subject = f"SparkMemo 每日提醒 · {today}"
    html = (
        f"<h3>SparkMemo 每日提醒</h3>"
        f"<p>日期：{today}</p>"
        f"<p>提醒内容正在生成中，详细模板将在后续版本上线。</p>"
    )
    return subject, html