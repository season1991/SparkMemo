# SparkMemo SQLAlchemy 模型
from datetime import date
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String, UniqueConstraint
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


# ========== DSP 上传模块（v0.5）==========


class DspUpload(Base):
    """DSP 周预测 Excel 批次元数据表。

    联合唯一 (vendor, item, sub_item, version_date) 阻断同版本重传；
    删除时由 SQLAlchemy 级联清空 dsp_upload_rows。
    """

    __tablename__ = "dsp_uploads"
    __table_args__ = (
        UniqueConstraint(
            "vendor",
            "item",
            "sub_item",
            "version_date",
            name="uk_dsp_upload_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False)
    item: Mapped[str] = mapped_column(String(128), nullable=False)
    sub_item: Mapped[str] = mapped_column(String(128), nullable=False)
    version_date: Mapped[str] = mapped_column(String(10), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(10), default=_today_str, nullable=False)

    rows: Mapped[list["DspUploadRow"]] = relationship(
        back_populates="upload",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DspUploadRow(Base):
    """DSP 周预测事实行表：每条记录 = (数据行 × 有效周列) 的展开。"""

    __tablename__ = "dsp_upload_rows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_id: Mapped[int] = mapped_column(
        ForeignKey("dsp_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    country: Mapped[Optional[str]] = mapped_column(String(64))
    category: Mapped[Optional[str]] = mapped_column(String(128))
    config_code: Mapped[Optional[str]] = mapped_column(String(128))
    config_name: Mapped[Optional[str]] = mapped_column(String(256))
    data_type: Mapped[Optional[str]] = mapped_column(String(64))
    ttl: Mapped[Optional[int]] = mapped_column(Integer)
    ym: Mapped[str] = mapped_column("ym", String(7), nullable=False)
    week: Mapped[str] = mapped_column(String(8), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    upload: Mapped["DspUpload"] = relationship(back_populates="rows")


# ========== DSP 上传模块结束 ==========


# ========== 透视查询（v0.5.6）==========


class WeekDt(Base):
    """日期周维度维表（外部维护，本项目只读引用）。

    - dt: 日期（YYYY-MM-DD）
    - year_id / month_id / week_id: ISO 年/自然月/ISO 周编号
    - is_week_start: 是否为周起始日（周一）
    """

    __tablename__ = "week_dt"

    dt: Mapped[str] = mapped_column(String(10), primary_key=True)
    year_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    week_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_week_start: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# ========== 透视查询 模块结束 ==========


# ========== 跨表数据填充（v0.6.0）==========


class CrossTableFillJob(Base):
    """跨表数据填充任务元数据表。

    三张表的顶层；上传即创建。状态机：pending → configured → executed / failed / expired。
    `target_headers` / `base_headers` 以 JSON 字符串存储，因 Excel 列名任意。
    """

    __tablename__ = "cross_table_fill_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target_filename: Mapped[str] = mapped_column(String(256), nullable=False)  # 原 target xlsx 文件名
    base_filename: Mapped[str] = mapped_column(String(256), nullable=False)    # 原 base xlsx 文件名
    target_headers: Mapped[str] = mapped_column(String(2000), nullable=False) # JSON 字符串
    base_headers: Mapped[str] = mapped_column(String(2000), nullable=False)   # JSON 字符串
    target_row_count: Mapped[int] = mapped_column(Integer, nullable=False)    # target 数据行数
    base_row_count: Mapped[int] = mapped_column(Integer, nullable=False)      # base 数据行数
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # 状态机
    result_row_count: Mapped[Optional[int]] = mapped_column(Integer)          # 执行后写入 target 行数
    filled_count: Mapped[Optional[int]] = mapped_column(Integer)              # ≥1 个 mapping 填充成功的行数
    unmatched_count: Mapped[Optional[int]] = mapped_column(Integer)           # base 缺该 key 的行数
    multi_match_count: Mapped[Optional[int]] = mapped_column(Integer)         # 命中 ≥2 行的行数
    created_at: Mapped[str] = mapped_column(String(10), default=_today_str, nullable=False)   # YYYY-MM-DD
    updated_at: Mapped[str] = mapped_column(String(10), default=_today_str, onupdate=_today_str, nullable=False)
    expires_at: Mapped[str] = mapped_column(String(10), nullable=False)       # YYYY-MM-DD；+24h

    rows: Mapped[list["CrossTableFillRow"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    config: Mapped[Optional["CrossTableFillConfig"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class CrossTableFillRow(Base):
    """跨表数据填充行明细表。role 字段统一存 target / base 两张表的全量数据。

    `data` 为 JSON 字符串，因 Excel 任意列名无法映射到固定 SQL 列。
    `key_value` 在 execute 阶段由配置归一化生成；非执行阶段为 NULL。
    """

    __tablename__ = "cross_table_fill_rows"
    __table_args__ = (
        # role 上加一个普通索引配合 FK 索引方便单边查询（target-only / base-only）
        {"mysql_engine": "InnoDB", "sqlite_with_rowid": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("cross_table_fill_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # target / base
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)           # 0-based，原 Excel 行号（不含表头）
    key_value: Mapped[Optional[str]] = mapped_column(String(1024))             # 主键值归一化拼接字符串
    data: Mapped[str] = mapped_column(String(8192), nullable=False)            # JSON 字符串，整行字段值字典

    job: Mapped["CrossTableFillJob"] = relationship(back_populates="rows")


class CrossTableFillConfig(Base):
    """跨表数据填充匹配配置表。job_id 同时是 PK 和 FK；一一对应。

    `target_keys` / `base_keys` / `mappings` 全部以 JSON 字符串存储。
    overwrite 模式下 `confirm_token` 必填；new_column only 时必为 None。
    """

    __tablename__ = "cross_table_fill_configs"

    job_id: Mapped[int] = mapped_column(
        ForeignKey("cross_table_fill_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    target_keys: Mapped[str] = mapped_column(String(512), nullable=False)  # JSON list[str]
    base_keys: Mapped[str] = mapped_column(String(512), nullable=False)    # JSON list[str]
    mappings: Mapped[str] = mapped_column(String(8192), nullable=False)     # JSON list[{base_field, target_field, mode}]
    join_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="left")         # left / inner
    match_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="merge_multi") # merge_multi / first / last
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trim_strings: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirm_token: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(10), default=_today_str, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(10), default=_today_str, onupdate=_today_str, nullable=False)

    job: Mapped["CrossTableFillJob"] = relationship(back_populates="config")


# ========== 跨表数据填充 模块结束 ==========