# 提醒服务 - 纯函数，无副作用
from __future__ import annotations

from datetime import date, timedelta
from typing import Final


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


# 提醒规则枚举（与后端 spec / OpenAPI RemindRule schema 对齐）
ON_DUE: Final = "on_due"
BEFORE_1D: Final = "before_1d"
BEFORE_2D: Final = "before_2d"
BEFORE_3D: Final = "before_3d"
BEFORE_1W: Final = "before_1w"
BEFORE_1M: Final = "before_1m"
CUSTOM: Final = "custom"

REMIND_RULES: Final[dict[str, tuple[str, int]]] = {
    # kind, value 解释：
    #   on_due       -> 不偏移
    #   days_before  -> 减 value 天
    #   weeks_before -> 减 value * 7 天（写死，不按周历）
    #   months_before-> 按日历月减 value 个月，目标日超过目标月末时 clamp 到该月最后一天
    #   custom       -> 取 custom_remind_start_at
    ON_DUE:        ("on_due", 0),
    BEFORE_1D:     ("days_before", 1),
    BEFORE_2D:     ("days_before", 2),
    BEFORE_3D:     ("days_before", 3),
    BEFORE_1W:     ("weeks_before", 1),
    BEFORE_1M:     ("months_before", 1),
    CUSTOM:        ("custom", 0),
}


def shift_month(d: date, months: int = -1) -> date:
    """
    日历月偏移；目标日超过目标月末时 clamp 到该月最后一天。

    用法:
        shift_month(date(2026, 3, 31), -1) == date(2026, 2, 28)  # 平年 clamp
        shift_month(date(2024, 3, 31), -1) == date(2024, 2, 29)  # 闰年 clamp
        shift_month(date(2026, 8, 15), -1) == date(2026, 7, 15)
        shift_month(date(2026, 1, 15), -1) == date(2025, 12, 15) # 跨年
    """
    y, m = d.year, d.month + months
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    # 目标月最后一天：取下月 1 日减 1 day
    if m == 12:
        next_month_first = date(y + 1, 1, 1)
    else:
        next_month_first = date(y, m + 1, 1)
    last_day = (next_month_first - timedelta(days=1)).day
    return date(y, m, min(d.day, last_day))


def resolve_remind_start_at(
    due_at: str,
    remind_rule: str,
    custom_remind_start_at: str | None = None,
) -> str:
    """
    根据 remind_rule 把业务意图「什么时候开始提醒」翻译为具体 YYYY-MM-DD。

    参数:
        due_at: 截止日，YYYY-MM-DD（已校验合法格式）
        remind_rule: REMIND_RULES 中的 key；非法时抛 ValueError
        custom_remind_start_at: 仅在 remind_rule='custom' 时必填；YYYY-MM-DD

    返回:
        str: 翻译后的提醒起始日，YYYY-MM-DD

    异常:
        ValueError: remind_rule 非法 / custom 模式缺 custom_remind_start_at / 翻译结果晚于 due_at
    """
    if remind_rule not in REMIND_RULES:
        raise ValueError(f"unknown remind_rule: {remind_rule!r}")

    end = date.fromisoformat(due_at)
    kind, value = REMIND_RULES[remind_rule]

    if kind == "on_due":
        resolved = end
    elif kind == "days_before":
        resolved = end - timedelta(days=value)
    elif kind == "weeks_before":
        resolved = end - timedelta(days=value * 7)
    elif kind == "months_before":
        resolved = shift_month(end, months=-value)
    elif kind == "custom":
        if not custom_remind_start_at:
            raise ValueError("custom 模式必须传 custom_remind_start_at")
        # 校验格式
        try:
            resolved = date.fromisoformat(custom_remind_start_at)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "custom_remind_start_at must be YYYY-MM-DD"
            ) from exc
    else:  # pragma: no cover - 防御性 fallback
        raise ValueError(f"unknown remind_rule kind: {kind!r}")

    resolved_str = resolved.isoformat()

    # 翻译后必须 <= due_at；否则认为用户选了非法组合（custom 模式可能错填未来日期）
    if resolved_str > due_at:
        raise ValueError(
            f"resolved remind_start_at ({resolved_str}) must be <= due_at ({due_at})"
        )

    return resolved_str


def infer_remind_rule(due_at: str, remind_start_at: str) -> str:
    """
    反推 remind_rule：精确匹配 7 档之一；不匹配返回 CUSTOM。

    用法: 编辑模式 UI 根据 (due_at, remind_start_at) 推断 select 当前选中档。
    - on_due:        due_at == remind_start_at
    - before_Nd:     due_at - remind_start_at == N 天
    - before_1w:     due_at - remind_start_at == 7 天
    - before_1m:     due_at == shift_month(remind_start_at, +1)  # 按日历月回推
    - 其余:          CUSTOM
    """
    if due_at == remind_start_at:
        return ON_DUE

    try:
        end = date.fromisoformat(due_at)
        start = date.fromisoformat(remind_start_at)
    except ValueError:
        return CUSTOM

    delta_days = (end - start).days
    if delta_days == 1:
        return BEFORE_1D
    if delta_days == 2:
        return BEFORE_2D
    if delta_days == 3:
        return BEFORE_3D
    if delta_days == 7:
        return BEFORE_1W
    if delta_days > 0 and shift_month(start, months=1) == end:
        return BEFORE_1M

    return CUSTOM
