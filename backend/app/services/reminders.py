# 提醒计划计算服务 - 纯函数，无副作用
from datetime import date, timedelta


def compute_reminders(remind_start_at: str, due_at: str) -> list[dict]:
    """
    返回 [remind_start_at, due_at] 闭区间内每日一条的提醒计划。

    参数:
        remind_start_at: 提醒起始日期，YYYY-MM-DD 格式字符串
        due_at: 截止日期，YYYY-MM-DD 格式字符串

    返回:
        list[dict]: 每项包含 remind_at 字段，例如 [{"remind_at": "2026-08-08"}, ...]
    """
    start = date.fromisoformat(remind_start_at)
    end = date.fromisoformat(due_at)
    days = (end - start).days + 1
    return [
        {"remind_at": (start + timedelta(days=i)).isoformat()}
        for i in range(days)
    ]