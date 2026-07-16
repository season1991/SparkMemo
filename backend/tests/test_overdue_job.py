import inspect
import re


# 验证逾期任务筛选、状态更新、幂等性及每日零点调度注册行为。


# 验证 today=2026-08-15 时 due_at=2026-08-10 已达到 3 天逾期阈值，pending 任务转为 overdue_done 并写入完成日。
def test_overdue_marks_task_overdue_done(
    make_company,
    make_project,
    make_task,
    db,
):
    import app.services.scheduler as scheduler

    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(
        db,
        company.id,
        project.id,
        due_at="2026-08-10",
        remind_start_at="2026-08-09",
    )

    check_overdue_tasks = getattr(scheduler, "check_overdue_tasks")
    check_overdue_tasks(db, today="2026-08-15")
    db.refresh(task)

    assert task.status == "overdue_done"
    assert task.completed_at == "2026-08-15"


# 验证 due_at=2026-08-13 距 today=2026-08-15 仅 2 天时不满足阈值，任务保持 pending。
def test_overdue_skips_within_3_days(make_company, make_project, make_task, db):
    import app.services.scheduler as scheduler

    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(
        db,
        company.id,
        project.id,
        due_at="2026-08-13",
        remind_start_at="2026-08-12",
    )

    check_overdue_tasks = getattr(scheduler, "check_overdue_tasks")
    check_overdue_tasks(db, today="2026-08-15")
    db.refresh(task)

    assert task.status == "pending"
    assert task.completed_at is None


# 验证 Job 仅处理 pending，已有 completed 状态的任务不会被改成 overdue_done 或覆盖完成日期。
def test_overdue_skips_completed(make_company, make_project, make_task, db):
    import app.services.scheduler as scheduler

    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(
        db,
        company.id,
        project.id,
        due_at="2026-08-10",
        remind_start_at="2026-08-09",
        status="completed",
        completed_at="2026-08-11",
    )

    check_overdue_tasks = getattr(scheduler, "check_overdue_tasks")
    check_overdue_tasks(db, today="2026-08-15")
    db.refresh(task)

    assert task.status == "completed"
    assert task.completed_at == "2026-08-11"


# 验证已经是 overdue_done 的任务不会重复处理，保留原有 completed_at 并维持状态不变。
def test_overdue_skips_already_overdue_done(
    make_company,
    make_project,
    make_task,
    db,
):
    import app.services.scheduler as scheduler

    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(
        db,
        company.id,
        project.id,
        due_at="2026-08-10",
        remind_start_at="2026-08-09",
        status="overdue_done",
        completed_at="2026-08-12",
    )

    check_overdue_tasks = getattr(scheduler, "check_overdue_tasks")
    check_overdue_tasks(db, today="2026-08-15")
    db.refresh(task)

    assert task.status == "overdue_done"
    assert task.completed_at == "2026-08-12"


# 验证 Job 重复执行具有幂等性：第一次标记后第二次执行不更新状态，也不把完成日期改为新日期。
def test_overdue_idempotent(make_company, make_project, make_task, db):
    import app.services.scheduler as scheduler

    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(
        db,
        company.id,
        project.id,
        due_at="2026-08-10",
        remind_start_at="2026-08-09",
    )

    check_overdue_tasks = getattr(scheduler, "check_overdue_tasks")
    check_overdue_tasks(db, today="2026-08-15")
    db.refresh(task)
    first_completed_at = task.completed_at
    check_overdue_tasks(db, today="2026-08-16")
    db.refresh(task)

    assert task.status == "overdue_done"
    assert task.completed_at == first_completed_at == "2026-08-15"


# 验证逾期 Job 将 cutoff 和 today 作为 SQL 参数传入，SQL 文本不包含数据库专用当前日期函数。
def test_overdue_sql_no_db_date_func(
    make_company,
    make_project,
    make_task,
    db,
    monkeypatch,
):
    import app.services.scheduler as scheduler

    company = make_company(db)
    project = make_project(db, company.id)
    make_task(
        db,
        company.id,
        project.id,
        due_at="2026-08-10",
        remind_start_at="2026-08-09",
    )
    statements = []
    execute = db.execute

    def capture(statement, *args, **kwargs):
        statements.append(str(statement))
        return execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", capture)
    check_overdue_tasks = getattr(scheduler, "check_overdue_tasks")
    check_overdue_tasks(db, today="2026-08-15")

    sql = "\n".join(statements).upper()
    assert not re.search(r"CURDATE\(\)|NOW\(\)|CURRENT_DATE|GETDATE\(\)", sql)
    assert ":CUTOFF" in sql or "?" in sql


# 验证 APScheduler 注册 check_overdue_tasks 的 cron 触发器，执行时间为每日 00:00。
def test_overdue_scheduler_registered():
    import app.services.scheduler as scheduler

    source = inspect.getsource(scheduler)
    assert "check_overdue_tasks" in source
    assert re.search(r"hour\s*=\s*0", source)
    assert re.search(r"minute\s*=\s*0", source)
