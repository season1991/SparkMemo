# SparkMemo Pydantic 模式
from datetime import date as _date
from typing import Literal, Optional

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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

# 24h 零填充 HH:MM 正则：[01]\d|2[0-3] 覆盖 00-23；[0-5]\d 覆盖 00-59
_HHMM_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_email(value: Optional[str], field_name: str) -> Optional[str]:
    """邮箱格式校验：非空时必须符合 user@domain.tld 形式；空值放行。"""
    if value is None or value == "":
        return value
    if not isinstance(value, str) or not _EMAIL_PATTERN.match(value):
        raise ValueError(f"{field_name} must be a valid email address")
    return value


def _validate_send_time(value: str) -> str:
    """调度时间校验：必须是 24h 零填充 HH:MM；非空、长度恰为 5。"""
    if not isinstance(value, str) or not _HHMM_PATTERN.match(value):
        raise ValueError("send_time must be HH:MM (24h, zero-padded)")
    return value


class EmailConfigWrite(BaseModel):
    """邮箱配置写入请求体：用于 PUT /api/email-config 的单行 upsert。

    - smtp_password 留空字符串或 None 视为「保留旧值」，由路由层处理；
    - send_time / active 每次 PUT 显式覆盖（与 smtp_password 行为不同）；
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
    send_time: str = "08:00"
    active: bool = False

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

    @field_validator("send_time")
    @classmethod
    def _check_send_time(cls, value: str) -> str:
        return _validate_send_time(value)


class EmailConfigRead(BaseModel):
    """邮箱配置响应体：未配置时 exists=false 且业务字段为 None / False。

    注意：响应**永远不回 smtp_password 明文**，用 smtp_password_set: bool 替代。
    send_time / active 始终回显，方便前端表单回填。
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
    send_time: str = "08:00"
    active: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ========== 邮箱配置 模块结束 ==========


# ========== DSP 上传（v0.5）模式 ==========


class DspUploadRead(BaseModel):
    """DSP 批次响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    vendor: str
    item: str
    sub_item: str
    version_date: str
    source_filename: str
    row_count: int
    created_at: str


class DspUploadListResponse(BaseModel):
    """DSP 批次列表分页响应。"""

    items: list[DspUploadRead]
    total: int
    page: int
    size: int


class DspUploadRowRead(BaseModel):
    """DSP 事实行响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    country: Optional[str] = None
    category: Optional[str] = None
    config_code: Optional[str] = None
    config_name: Optional[str] = None
    data_type: Optional[str] = None
    ttl: Optional[int] = None
    ym: str
    week: str
    date: str
    quantity: int


class DspUploadRowListResponse(BaseModel):
    """DSP 事实行分页响应。"""

    items: list[DspUploadRowRead]
    total: int
    page: int
    size: int


# ========== DSP 上传 模块结束 ==========


# ========== 透视查询（v0.5.6）模式 ==========


# 透视类型：'demand' 固定 Demand 数据；'demand_plus_supply' 同时取 Demand + Supply 并派生 TTL_GAP / Rolling_TTLGAP
PivotType = Literal["demand", "demand_plus_supply"]


class PivotQueryRequest(BaseModel):
    """透视查询请求体。

    入参分四组：
    1. 必填定位：`pivot_type` / `vendor` / `item` / `sub_item` / `version_dates`
       - `pivot_type='demand'`：1-20 个 version_dates（多选）
       - `pivot_type='demand_plus_supply'`：仅 1 个 version_date（单选，超限 → 422）
    2. 横向业务行筛选（可选）：`countries` / `categories` / `config_codes` / `config_names`
       - **严格级联**：`config_names` 提供 → 必须提供 `categories` → 必须提供 `countries`
    3. 纵向日期筛选（可选）：`years` / `months` / `weeks`
       - **级联**：`weeks` 提供 → 必须同时提供 `months` 与 `years`
       - **级联**：`months` 提供 → 必须提供 `years`
       - **至少一个**：必须提供 `years` / `months` / `weeks` 其一
    4. 展示控制：`expand_to_daily`（默认 False = 按周；True = 按日）

    `pivot_type='demand'` 时固定注入 `data_type='Demand'` 过滤；
    `pivot_type='demand_plus_supply'` 时改为 `data_type IN ('Demand', 'Supply')`，并在响应中
    Python 层派生 `TTL_GAP` / `Rolling_TTLGAP` 两行（详见 spec §11）。
    """

    pivot_type: PivotType = "demand"
    vendor: str = Field(min_length=1, max_length=64)
    item: str = Field(min_length=1, max_length=128)
    sub_item: str = Field(min_length=1, max_length=128)
    version_dates: list[str] = Field(min_length=1, max_length=20)

    countries: Optional[list[str]] = None
    categories: Optional[list[str]] = None
    config_codes: Optional[list[str]] = None
    config_names: Optional[list[str]] = None

    years: Optional[list[int]] = None
    months: Optional[list[int]] = None
    weeks: Optional[list[int]] = None
    expand_to_daily: bool = False

    @field_validator("version_dates")
    @classmethod
    def _check_version_dates(cls, value: list[str]) -> list[str]:
        for i, vd in enumerate(value):
            try:
                _validate_yyyy_mm_dd(vd, f"version_dates[{i}]")
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
        return value

    @field_validator("months")
    @classmethod
    def _check_months(cls, value: Optional[list[int]]) -> Optional[list[int]]:
        if value is not None:
            for m in value:
                if not (1 <= m <= 12):
                    raise ValueError(f"months must be in 1-12, got {m}")
        return value

    @field_validator("weeks")
    @classmethod
    def _check_weeks(cls, value: Optional[list[int]]) -> Optional[list[int]]:
        if value is not None:
            for w in value:
                if not (1 <= w <= 53):
                    raise ValueError(f"weeks must be in 1-53, got {w}")
        return value

    @model_validator(mode="after")
    def _check_cascade(self):
        # 业务行级联：config_names → categories → countries
        if self.config_names and not self.categories:
            raise ValueError(
                "categories is required when config_names is provided"
            )
        if self.categories and not self.countries:
            raise ValueError(
                "countries is required when categories is provided"
            )

        # 时间维度级联：weeks → (months AND years) → years
        if self.weeks:
            if not (self.years and self.months):
                raise ValueError(
                    "years and months are required when weeks is provided"
                )
        if self.months and not self.years:
            raise ValueError("years is required when months is provided")

        # 时间维度至少一个
        if not (self.years or self.months or self.weeks):
            raise ValueError(
                "at least one of years / months / weeks must be provided"
            )

        # v0.5.7：demand_plus_supply 模式仅支持单个 version_date（单选）。
        # 因 TTL_GAP / Rolling_TTLGAP 按 version_date 单独成行，
        # 多版本会让行数膨胀到不可控；故在模型层阻断。
        if self.pivot_type == "demand_plus_supply" and len(self.version_dates) != 1:
            raise ValueError(
                "pivot_type='demand_plus_supply' only supports a single "
                "version_date; please provide exactly 1 element in "
                "version_dates (got %d)" % len(self.version_dates)
            )

        return self


class PivotRow(BaseModel):
    """透视表的一行（横向）：业务维度组合 + 多个版本日期的 quantity 列。

    `quantities` 字典的 key 是 `period_date`（按周为周起始日，按日为每天），
    value 是 quantity（缺失时由后端 COALESCE 为 0）。
    """

    country: Optional[str] = None
    category: Optional[str] = None
    config_code: Optional[str] = None
    config_name: Optional[str] = None
    data_type: Optional[str] = None
    ttl: Optional[int] = None
    version_date: str
    quantities: dict[str, int]


class PivotQueryResponse(BaseModel):
    """透视查询响应。

    - `period_columns`：纵向展开成列头的日期列表（升序），前端用作表头
    - `row_groups`：横向分组的行列表，每行包含业务维度 + 各 period 的 quantity
    - `date_granularity`：标识返回的 period 是按周（"week"）还是按日（"day"）
    """

    period_columns: list[str]
    row_groups: list[PivotRow]
    total_rows: int
    version_dates: list[str]
    date_granularity: Literal["week", "day"]


class WeekInfo(BaseModel):
    """透视查询辅助：单条「ISO 周编号 + 周起始日（周一）」映射。

    - `week_id`：ISO 周编号（1-53）
    - `week_start_date`：该周周一的日期（YYYY-MM-DD）

    注：ISO 周历下，周一为一周的第一天；week_id 归属的「ISO 年」与 `week_start_date`
    的自然年可能不同（如 2025-W01 起始于 2024-12-30）。
    """

    week_id: int
    week_start_date: str


# ========== 透视查询 模块结束 ==========
