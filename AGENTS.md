# HRMS 项目级 Codex 规则

## Python 环境

- 使用 conda 管理 Python 环境，环境名固定为 `dev_env`。
- 任何 Python 操作（安装依赖、运行后端、跑 pytest、执行脚本）之前，必须先激活该环境：

  ```bash
  conda activate dev_env
  ```

- 不要在未激活 `dev_env` 的情况下执行 `pip install`、`python`、`uvicorn`、`pytest` 等命令。
- 依赖统一写到 `backend/requirements.txt`，不要在 `dev_env` 之外另起虚拟环境。
- 如果 `dev_env` 不存在或损坏，先停下来告诉用户，不要自行重建环境。

## 关键约定：shell 激活环境的正确写法

PowerShell 单行写法 `conda activate dev_env; pytest ...` **不会真正切换环境**——`conda activate` 需要修改当前 shell 进程的环境变量，单行命令在子 shell 中执行完毕后父 shell 环境不变。看似激活了，实际跑的是上一个 conda 环境的 python（通常是 `trae_env`）。

**正确的写法（二选一）**：

**方式 A：分两行写（推荐，行为最清晰）**

```powershell
conda activate dev_env
pytest backend/tests -v
```

**方式 B：用绝对路径直接调用 dev_env 的 python（CI / 脚本场景）**

```powershell
& "D:\anaconda3\envs\dev_env\python.exe" -m pytest backend/tests -v
& "D:\anaconda3\envs\dev_env\python.exe" -m uvicorn app.main:app
& "D:\anaconda3\envs\dev_env\python.exe" -m pip install -r backend/requirements.txt
```

**如何确认当前用的是 dev_env**：

```powershell
& "D:\anaconda3\envs\dev_env\python.exe" -c "import sys; print(sys.executable)"
# 必须输出：D:\anaconda3\envs\dev_env\python.exe
```

如果输出的是 `D:\anaconda3\envs\trae_env\python.exe` 或其他路径，说明环境错了，必须停下来排查，不要继续操作。

## 历史教训（2026-07-12）

在 `conda activate dev_env; pytest ...` 单行写法下跑测试，dev_env 实际未被激活，跑的是 trae_env。trae_env 的 `bcrypt` 版本与 `passlib 1.7.4` 兼容（运气好），所以测试"看似通过"；但 dev_env 实际装着 `bcrypt==5.0.0`，与 `passlib 1.7.4` **不兼容**（`bcrypt.__about__` 在 4.x 被删除），导致用户在自己环境跑测试时所有需要 `get_password_hash` 的用例在 setup 阶段 ERROR，最终只剩 TC01 通过。

修复方法：在 dev_env 里 `pip install bcrypt==4.0.1`（与 `requirements.txt` 一致）。

**后续严格执行本文件 §"shell 激活环境的正确写法"**，避免再次出现"环境用错但结果看似通过"的假象。