# SparkMemo 任务提醒系统 - 项目规格

## 1. 项目概述

SparkMemo 是一个单用户本地版任务提醒 Web 应用。用户可自定义任务类型、紧急程度、提前提醒时机（多档预设 + 自定义时间），系统在指定时间通过浏览器系统通知 + 页面弹窗双重方式提醒，并对逾期 3 天的任务自动标记为完成。

> Spark（阈值触发）+ Memo（备忘录），寓意「达到阈值即刻弹出备忘提醒」。

## 2. 技术栈

### 前端技术栈

| 技术 | 说明 |
|------|------|
| Vue 3 | 前端框架（Composition API） |
| Vite 5 | 构建工具 |
| Element Plus | UI 组件库（中文友好） |
| Pinia | 状态管理 |
| Vue Router 4 | 路由管理 |
| Axios | HTTP 请求库 |
| WebSocket API | 实时通知通道 |

### 后端技术栈

| 技术 | 说明 |
|------|------|
| Python 3.10+ | 编程语言 |
| FastAPI | Web 框架（异步 + 自动 OpenAPI） |
| SQLAlchemy 2.0 | ORM |
| Pydantic v2 | 数据校验 |
| pydantic-settings | 配置管理（.env 多源加载） |
| MySQL 8.0 | 数据库 |
| PyMySQL + cryptography | MySQL 驱动 |
| APScheduler | 定时调度（提醒扫描 + 逾期处理） |
| WebSocket | 实时推送通知到浏览器 |

## 3. 项目结构

```
SparkMemo/
├── frontend/                  # 前端项目
│   ├── public/                # 静态资源
│   └── src/
│       ├── api/               # 接口封装
│       ├── components/        # 公共组件
│       ├── views/             # 页面组件
│       ├── stores/            # Pinia 状态
│       ├── router/            # 路由
│       ├── App.vue            # 根组件（WebSocket + 全局通知）
│       └── main.js
│
├── backend/                   # 后端项目
│   ├── app/
│   │   ├── api/               # 路由（tasks / task_types / notifications / ws）
│   │   ├── crud/              # 数据库操作
│   │   ├── services/          # 业务逻辑（APScheduler）
│   │   ├── models.py          # SQLAlchemy 模型
│   │   ├── schemas.py         # Pydantic 模式
│   │   ├── config.py          # 配置
│   │   ├── database.py        # 数据库连接
│   │   ├── deps.py            # 依赖项
│   │   ├── ws_manager.py      # WebSocket 连接管理
│   │   └── main.py            # 应用入口
│   ├── static/                # 前端构建产物（Vite build 输出）
│   ├── spec/                  # 规格文档（含本 README）
│   ├── .env.example
│   └── requirements.txt
│
├── start.bat / start.sh       # 启动脚本
├── .gitignore
└── README.md
```

> 说明：未来可按 HRMS 模板演进，新增 `backend/openapi/`（自动生成接口契约）、`backend/tests/`（测试）、`backend/.todo/`（任务清单）等子目录。

## 4. 功能模块

| 模块 | 查阅文章 | 完成情况 |
|:-----|:---------|:--------:|
| 任务管理 | [./task_management.md](./task_management.md) | [x] 已完成 |
| 今日概述 | [./dashboard.md](./dashboard.md) | [ ] 未完成 |


## 5. 开发规范

### 5.1 开发流程

每个功能模块按以下阶段推进：

1. **先 spec 讨论再开发**：功能开发前先在 `backend/spec/` 形成/更新规格文档
2. **生成 Todo List**：按规格将开发任务拆分为 todo，存放于 `backend/.todo/<模块名>.md`，含 `[ ]` / `[x]` 状态标记
3. **测试驱动（全红）**：先在 `backend/tests/` 写测试用例，运行确认全部失败
4. **测试驱动后端开发（全绿）**：实现 `app/` 下的代码，直到测试全部通过
5. **生成 OpenAPI**：保存至 `backend/openapi/`
6. **更新 Todo List**：每完成一项标记 `[x]`

| 阶段 | 产出物 | 存放位置 |
|------|--------|----------|
| 需求确认 | 规格文档 | `backend/spec/` |
| 接口契约 | OpenAPI 文档 | `backend/openapi/` |
| 测试验证 | 测试用例 | `backend/tests/` |
| 功能实现 | 代码 | `backend/app/` |
| 开发计划 | Todo List | `backend/.todo/` |

### 5.2 代码注释规范

代码中必须包含清晰的中文注释，确保可读性与团队协作效率。

#### 注释要求

| 文件类型 | 注释要求 | 示例 |
|----------|----------|------|
| 路由文件 (`api/*.py`) | 每个接口必须注释功能说明、请求参数、响应格式 | `# 获取任务列表，支持 status / page / size 过滤` |
| Service 文件 (`services/*.py`) | 每个方法必须注释业务逻辑、异常情况 | `# 扫描到期提醒：遍历 pending 任务，按 offset 计算触发时间并推送` |
| CRUD 文件 (`crud/*.py`) | 每个方法必须注释数据库操作 | `# 根据 id 查询任务，关联 task_type` |
| Model 文件 (`models.py`) | 每个字段必须注释含义和约束 | `# status: pending / completed / overdue_done` |
| Schema 文件 (`schemas.py`) | 每个字段必须注释用途和校验规则 | `# due_date: 到期日，必须晚于当前时间` |
| 工具/核心文件 (`config.py` / `database.py` / `ws_manager.py`) | 每个方法/类必须注释功能和使用场景 | `# WebSocket 连接管理器：维护在线客户端字典，支持广播` |

#### 注释风格

```python
# 模块文件顶部必须包含模块说明
"""提醒调度服务 - APScheduler 定时扫描任务并触发通知"""

# 类定义必须包含类说明
class Task(Base):
    """任务表模型"""
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 主键，自增
    title: Mapped[str] = mapped_column(String(128))  # 任务标题，1-128 字符

# 方法定义必须包含方法说明和参数说明
def scan_reminders(db: Session) -> list[Notification]:
    """
    扫描到期提醒并推送 WebSocket 通知

    参数:
        db: 数据库会话

    返回:
        list[Notification]: 本次新创建的通知列表

    异常:
        DatabaseError: 查询任务或写入通知失败
    """
```

#### 注释禁止事项

- 禁止使用纯英文注释（变量名、库函数名除外）
- 禁止注释与代码功能不符
- 禁止留下无意义占位注释（如 `# TODO`、`# xxx`）
- 注释应简洁明了，避免冗长描述

### 5.3 命名与目录约定

- Python：模块/包名 `snake_case`、类名 `PascalCase`、函数/变量 `snake_case`
- Vue：组件文件 `PascalCase.vue`（如 `TaskForm.vue`），stores `useXxxStore.js`
- API 路径：复数名词（`/api/tasks`、`/api/task-types`）
- 数据库表名：复数 `snake_case`（`task_types`、`notifications`）
- 状态枚举值：小写字符串（`pending` / `completed` / `overdue_done`）
