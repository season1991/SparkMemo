# SparkMemo SQLAlchemy 模型
from datetime import date
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _today_str() -> str:
    """返回当前日期的 10 字符 YYYY-MM-DD 字符串，供 created_at/updated_at 默认值使用。"""
    return date.today().isoformat()


class Company(Base):
    """公司表模型：存储客户公司基础信息。"""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(2000))
    created_at: Mapped[str] = mapped_column(String(10), default=_today_str, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        String(10), default=_today_str, onupdate=_today_str, nullable=False
    )

    projects: Mapped[list["Project"]] = relationship(back_populates="company")
    tasks: Mapped[list["Task"]] = relationship(back_populates="company")


class Project(Base):
    """项目表模型：隶属于公司，同公司下项目名唯一。"""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uk_company_project_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(2000))
    created_at: Mapped[str] = mapped_column(String(10), default=_today_str, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        String(10), default=_today_str, onupdate=_today_str, nullable=False
    )

    company: Mapped["Company"] = relationship(back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class TaskType(Base):
    """任务类型字典表：全表唯一，供任务外键引用。"""

    __tablename__ = "task_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[str] = mapped_column(String(10), default=_today_str, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        String(10), default=_today_str, onupdate=_today_str, nullable=False
    )

    tasks: Mapped[list["Task"]] = relationship(back_populates="task_type")


class Task(Base):
    """任务表模型：包含截止日期、提醒起始日期、状态流转与外键引用。"""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(4000))
    task_type_id: Mapped[Optional[int]] = mapped_column(ForeignKey("task_types.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    due_at: Mapped[str] = mapped_column(String(10), nullable=False)
    remind_start_at: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[str] = mapped_column(String(10), default=_today_str, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        String(10), default=_today_str, onupdate=_today_str, nullable=False
    )
    completed_at: Mapped[Optional[str]] = mapped_column(String(10))

    company: Mapped["Company"] = relationship(back_populates="tasks")
    project: Mapped["Project"] = relationship(back_populates="tasks")
    task_type: Mapped[Optional["TaskType"]] = relationship(back_populates="tasks")


class EmailConfig(Base):
    """邮箱配置表（单行表）。

    应用层固定以 id=1 读写；承担「SMTP 凭证 + 发件人 + 收件人 + 调度开关」的存储职责。
    调度字段 send_time / active 由 v0.4 引入；既有 MySQL 实例升级通过 lifespan 幂等 ALTER。
    """

    __tablename__ = "email_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    smtp_host: Mapped[str] = mapped_column(String(128), nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False)
    smtp_user: Mapped[str] = mapped_column(String(128), nullable=False)
    smtp_password: Mapped[str] = mapped_column(String(256), nullable=False)
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sender_email: Mapped[str] = mapped_column(String(128), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(128), nullable=False)
    recipient_name: Mapped[Optional[str]] = mapped_column(String(64))
    send_time: Mapped[str] = mapped_column(String(5), nullable=False, default="08:00")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(String(10), default=_today_str, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        String(10), default=_today_str, onupdate=_today_str, nullable=False
    )