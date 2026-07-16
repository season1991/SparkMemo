# SparkMemo Pydantic 模式
from datetime import date as _date
from typing import Optional

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


class TaskBase(BaseModel):
    """任务基础字段：title 必填，日期字段由 field_validator 校验 YYYY-MM-DD。"""

    title: str
    description: Optional[str] = None
    task_type_id: Optional[int] = None
    due_at: str
    remind_start_at: Optional[str] = None

    @field_validator("due_at")
    @classmethod
    def _check_due_at(cls, value: str) -> str:
        return _validate_yyyy_mm_dd(value, "due_at")

    @field_validator("remind_start_at")
    @classmethod
    def _check_remind_start_at(cls, value: Optional[str]) -> Optional[str]:
        return _validate_yyyy_mm_dd(value, "remind_start_at")


class TaskCreate(TaskBase):
    """创建任务请求体：company_id/project_id 由端点层校验，缺失返回 400。"""

    company_id: Optional[int] = None
    project_id: Optional[int] = None


class TaskUpdate(BaseModel):
    """更新任务请求体：全量替换字段，日期字段由 field_validator 校验。"""

    title: str
    description: Optional[str] = None
    task_type_id: Optional[int] = None
    company_id: int
    project_id: int
    due_at: str
    remind_start_at: str

    @field_validator("due_at")
    @classmethod
    def _check_due_at(cls, value: str) -> str:
        return _validate_yyyy_mm_dd(value, "due_at")

    @field_validator("remind_start_at")
    @classmethod
    def _check_remind_start_at(cls, value: str) -> str:
        return _validate_yyyy_mm_dd(value, "remind_start_at")


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
    """任务响应体：包含外键引用对象和实时计算的提醒计划。"""

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