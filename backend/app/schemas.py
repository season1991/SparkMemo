# SparkMemo Pydantic 模式
from datetime import date as _date
from typing import Literal, Optional

import re

from pydantic import BaseModel, ConfigDict, field_validator


def _validate_yyyy_mm_dd(value: Optional[str], field_name: str) -> Optional[str]:
    """校验 YYYY-MM-DD 格式；端点层捕获 ValueError 后返回 400。"""
    if value is None:
        return value
    try:
        _date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc
    return value


# 提醒规则枚举（与后端 spec RemindRule / OpenAPI RemindRule schema 对齐）
RemindRule = Literal[
    "on_due",
    "before_1d",
    "before_2d",
    "before_3d",
    "before_1w",
    "before_1m",
    "custom",
]


class CompanyBase(BaseModel):
    """公司基础字段：name 必填且全表唯一，notes 可空。"""

    name: str
    notes: Optional[str] = None


class CompanyCreate(CompanyBase):
    """创建公司请求体：name 缺失时由 Pydantic 返回 422。"""

    pass


class CompanyUpdate(CompanyBase):
    """更新公司请求体：全量替换 name 和 notes。"""

    pass


class CompanyRead(CompanyBase):
    """公司响应体：包含数据库生成的 id 和时间戳。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: str
    updated_at: str


class CompanyListResponse(BaseModel):
    """公司列表分页响应：items + total。"""

    items: list[CompanyRead]
    total: int


class ProjectBase(BaseModel):
    """项目基础字段：name 必填，notes 可空；company_id 由端点校验。"""

    name: str
    notes: Optional[str] = None


class ProjectCreate(BaseModel):
    """创建项目请求体：company_id 由端点校验存在性（422），缺失返回 400。"""

    company_id: Optional[int] = None
    name: str
    notes: Optional[str] = None


class ProjectUpdate(BaseModel):
    """更新项目请求体：全量替换字段。"""

    company_id: Optional[int] = None
    name: str
    notes: Optional[str] = None


class ProjectRead(BaseModel):
    """项目响应体：包含归属公司 id 和时间戳。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    name: str
    notes: Optional[str] = None
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    """项目列表分页响应。"""

    items: list[ProjectRead]
    total: int


class TaskTypeBase(BaseModel):
    """任务类型基础字段：name 必填且全表唯一。"""

    name: str


class TaskTypeCreate(TaskTypeBase):
    """创建任务类型请求体。"""

    pass


class TaskTypeUpdate(TaskTypeBase):
    """更新任务类型请求体。"""

    pass


class TaskTypeRead(TaskTypeBase):
    """任务类型响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: str
    updated_at: str


class TaskCreate(BaseModel):
    """创建任务请求体。

    入参使用业务意图 remind_rule（不允许直接传 remind_start_at）：
    - on_due / before_1d / before_2d / before_3d / before_1w / before_1m：
      custom_remind_start_at 设为 None；后端按 due_at 翻译出最终 remind_start_at；
    - custom：custom_remind_start_at 必填（YYYY-MM-DD）；后端原文使用。
    """

    title: str
    description: Optional[str] = None
    task_type_id: Optional[int] = None
    company_id: int
    project_id: int
    due_at: str
    remind_rule: RemindRule
    custom_remind_start_at: Optional[str] = None

    @field_validator("due_at")
    @classmethod
    def _check_due_at(cls, value: str) -> str:
        return _validate_yyyy_mm_dd(value, "due_at")

    @field_validator("custom_remind_start_at")
    @classmethod
    def _check_custom_remind(cls, value: Optional[str]) -> Optional[str]:
        return _validate_yyyy_mm_dd(value, "custom_remind_start_at")


class TaskUpdate(TaskCreate):
    """更新任务请求体：与 TaskCreate 字段一致；remind_start_at 不直接接收。"""

    pass


class TaskTypeRef(BaseModel):
    """任务类型引用对象，用于任务详情响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TaskCompanyRef(BaseModel):
    """公司引用对象，用于任务详情响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TaskProjectRef(BaseModel):
    """项目引用对象，用于任务详情响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ReminderItem(BaseModel):
    """单条提醒计划项。"""

    remind_at: str


class TaskRead(BaseModel):
    """任务响应体：包含外键引用对象和实时计算的提醒计划。

    注：响应只回 remind_start_at（最终日期），不回 remind_rule（业务意图不入库）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    task_type: Optional[TaskTypeRef] = None
    company: TaskCompanyRef
    project: TaskProjectRef
    due_at: str
    remind_start_at: str
    status: str
    completed_at: Optional[str] = None
    created_at: str
    updated_at: str
    reminders: list[ReminderItem] = []


class TaskListResponse(BaseModel):
    """任务列表分页响应。"""

    items: list[TaskRead]
    total: int


# ========== 今日概述（Dashboard）模式 ==========

class DashboardCompanyCount(BaseModel):
    """今日概述 - 单家公司在三档上的任务计数（含 total）。"""

    company_id: int
    company_name: str
    urgent: int
    due_soon: int
    early: int
    total: int


class DashboardSummary(BaseModel):
    """今日概述 - 全局合计；字段值 = companies[] 同名字段求和（单一真理源）。"""

    urgent: int
    due_soon: int
    early: int
    total: int


class DashboardTodayResponse(BaseModel):
    """今日概述响应：today + summary + companies[]。"""

    today: str
    summary: DashboardSummary
    companies: list[DashboardCompanyCount] = []


# ========== 今日概述 模块结束 ==========


# ========== 邮箱配置（Email Config）模式 ==========

# 简单邮箱格式校验正则：足够满足 spec 中「邮箱格式非法 → 400」要求，
# 避免引入 pydantic.EmailStr 强依赖的 email-validator 包。
_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _validate_email(value: Optional[str], field_name: str) -> Optional[str]:
    """邮箱格式校验：非空时必须符合 user@domain.tld 形式；空值放行。"""
    if value is None or value == "":
        return value
    if not isinstance(value, str) or not _EMAIL_PATTERN.match(value):
        raise ValueError(f"{field_name} must be a valid email address")
    return value


class EmailConfigWrite(BaseModel):
    """邮箱配置写入请求体：用于 PUT /api/email-config 的单行 upsert。

    - smtp_password 留空字符串或 None 视为「保留旧值」，由路由层处理；
    - 字段校验失败时 Pydantic 默认抛 422，由路由层映射为 400 满足 spec 错误约定。
    """

    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: Optional[str] = None
    use_tls: bool = True
    sender_email: str
    sender_name: str
    recipient_email: str
    recipient_name: Optional[str] = None

    @field_validator("smtp_host")
    @classmethod
    def _check_smtp_host(cls, value: str) -> str:
        if not (1 <= len(value) <= 128):
            raise ValueError("smtp_host length must be 1-128")
        return value

    @field_validator("smtp_port")
    @classmethod
    def _check_smtp_port(cls, value: int) -> int:
        if not (1 <= value <= 65535):
            raise ValueError("smtp_port must be in 1-65535")
        return value

    @field_validator("smtp_user")
    @classmethod
    def _check_smtp_user(cls, value: str) -> str:
        if not (1 <= len(value) <= 128):
            raise ValueError("smtp_user length must be 1-128")
        return value

    @field_validator("sender_email")
    @classmethod
    def _check_sender_email(cls, value: str) -> str:
        return _validate_email(value, "sender_email")

    @field_validator("recipient_email")
    @classmethod
    def _check_recipient_email(cls, value: str) -> str:
        return _validate_email(value, "recipient_email")

    @field_validator("sender_name")
    @classmethod
    def _check_sender_name(cls, value: str) -> str:
        if not (1 <= len(value) <= 64):
            raise ValueError("sender_name length must be 1-64")
        return value


class EmailConfigRead(BaseModel):
    """邮箱配置响应体：未配置时 exists=false 且所有字段为 None / False。

    注意：响应**永远不回 smtp_password 明文**，用 smtp_password_set: bool 替代。
    """

    exists: bool
    id: Optional[int] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password_set: bool = False
    use_tls: bool = False
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ========== 邮箱配置 模块结束 ==========
