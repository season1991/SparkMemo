"""remind_rule 翻译 + 反推 + shift_month 单元测试。"""

import pytest


# ---------- shift_month ----------

class TestShiftMonth:
    """shift_month 日历月偏移：覆盖年末/月末 clamp/闰年。"""

    def test_basic_month_minus_one(self):
        from datetime import date
        from app.services.reminders import shift_month

        assert shift_month(date(2026, 8, 15), -1) == date(2026, 7, 15)

    def test_cross_year(self):
        from datetime import date
        from app.services.reminders import shift_month

        # 1 月减 1 个月 → 上年 12 月
        assert shift_month(date(2026, 1, 15), -1) == date(2025, 12, 15)

    def test_non_leap_clamp(self):
        """2026-03-31 - 1 月 → 2026-02-28（平年）。"""
        from datetime import date
        from app.services.reminders import shift_month

        assert shift_month(date(2026, 3, 31), -1) == date(2026, 2, 28)

    def test_leap_clamp(self):
        """2024-03-31 - 1 月 → 2024-02-29（闰年）。"""
        from datetime import date
        from app.services.reminders import shift_month

        assert shift_month(date(2024, 3, 31), -1) == date(2024, 2, 29)

    def test_month_end_no_clamp_needed(self):
        from datetime import date
        from app.services.reminders import shift_month

        # 2026-08-31 - 1 月 → 2026-07-31（两端都是月末，恰好）
        assert shift_month(date(2026, 8, 31), -1) == date(2026, 7, 31)

    def test_zero_months_noop(self):
        from datetime import date
        from app.services.reminders import shift_month

        assert shift_month(date(2026, 8, 15), 0) == date(2026, 8, 15)


# ---------- resolve_remind_start_at ----------

class TestResolveRemindStartAt:
    """resolve_remind_start_at 翻译：覆盖 7 档。"""

    def test_on_due(self):
        from app.services.reminders import resolve_remind_start_at

        assert resolve_remind_start_at("2026-08-15", "on_due") == "2026-08-15"

    def test_before_1d(self):
        from app.services.reminders import resolve_remind_start_at

        assert resolve_remind_start_at("2026-08-15", "before_1d") == "2026-08-14"

    def test_before_2d(self):
        from app.services.reminders import resolve_remind_start_at

        assert resolve_remind_start_at("2026-08-15", "before_2d") == "2026-08-13"

    def test_before_3d(self):
        from app.services.reminders import resolve_remind_start_at

        assert resolve_remind_start_at("2026-08-15", "before_3d") == "2026-08-12"

    def test_before_1w_is_seven_days(self):
        """before_1w 固定写死 7 天（不按周历）。"""
        from app.services.reminders import resolve_remind_start_at

        assert resolve_remind_start_at("2026-08-15", "before_1w") == "2026-08-08"

    def test_before_1m_normal(self):
        from app.services.reminders import resolve_remind_start_at

        assert resolve_remind_start_at("2026-08-15", "before_1m") == "2026-07-15"

    def test_before_1m_clamp_non_leap(self):
        from app.services.reminders import resolve_remind_start_at

        assert resolve_remind_start_at("2026-03-31", "before_1m") == "2026-02-28"

    def test_before_1m_clamp_leap(self):
        from app.services.reminders import resolve_remind_start_at

        assert resolve_remind_start_at("2024-03-31", "before_1m") == "2024-02-29"

    def test_custom_with_date(self):
        from app.services.reminders import resolve_remind_start_at

        assert (
            resolve_remind_start_at(
                "2026-08-15", "custom", custom_remind_start_at="2026-08-10"
            )
            == "2026-08-10"
        )

    def test_custom_missing_date_raises(self):
        from app.services.reminders import resolve_remind_start_at

        with pytest.raises(ValueError, match="custom"):
            resolve_remind_start_at("2026-08-15", "custom", custom_remind_start_at=None)

    def test_custom_invalid_date_format_raises(self):
        from app.services.reminders import resolve_remind_start_at

        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            resolve_remind_start_at(
                "2026-08-15", "custom", custom_remind_start_at="2026/08/10"
            )

    def test_custom_date_after_due_raises(self):
        from app.services.reminders import resolve_remind_start_at

        with pytest.raises(ValueError, match="must be <= due_at"):
            resolve_remind_start_at(
                "2026-08-15", "custom", custom_remind_start_at="2026-08-16"
            )

    def test_unknown_rule_raises(self):
        from app.services.reminders import resolve_remind_start_at

        with pytest.raises(ValueError, match="unknown remind_rule"):
            resolve_remind_start_at("2026-08-15", "before_5d")


# ---------- infer_remind_rule ----------

class TestInferRemindRule:
    """infer_remind_rule 反推：用于编辑表单初始 select 值。"""

    def test_infer_on_due(self):
        from app.services.reminders import infer_remind_rule, ON_DUE

        assert infer_remind_rule("2026-08-15", "2026-08-15") == ON_DUE

    def test_infer_before_1d(self):
        from app.services.reminders import infer_remind_rule, BEFORE_1D

        assert infer_remind_rule("2026-08-15", "2026-08-14") == BEFORE_1D

    def test_infer_before_2d(self):
        from app.services.reminders import infer_remind_rule, BEFORE_2D

        assert infer_remind_rule("2026-08-15", "2026-08-13") == BEFORE_2D

    def test_infer_before_3d(self):
        from app.services.reminders import infer_remind_rule, BEFORE_3D

        assert infer_remind_rule("2026-08-15", "2026-08-12") == BEFORE_3D

    def test_infer_before_1w(self):
        from app.services.reminders import infer_remind_rule, BEFORE_1W

        assert infer_remind_rule("2026-08-15", "2026-08-08") == BEFORE_1W

    def test_infer_before_1m(self):
        from app.services.reminders import infer_remind_rule, BEFORE_1M

        assert infer_remind_rule("2026-08-15", "2026-07-15") == BEFORE_1M

    def test_infer_non_preset_falls_back_to_custom(self):
        """任意非预设偏移都归为 custom（如提前 10 天）。"""
        from app.services.reminders import infer_remind_rule, CUSTOM

        assert infer_remind_rule("2026-08-15", "2026-08-05") == CUSTOM

    def test_infer_invalid_format_falls_back_to_custom(self):
        from app.services.reminders import infer_remind_rule, CUSTOM

        assert infer_remind_rule("2026-08-15", "bad-format") == CUSTOM


# ---------- end-to-end: API 集成 ----------

class TestApiRemindRuleIntegration:
    """通过 POST/PUT 接口验证整链路翻译。"""

    async def test_create_task_before_1m_via_api(
        self, client, make_company, make_project, db
    ):
        from app import models

        company = models.Company(name="custom_compat_1")
        db.add(company)
        db.commit()
        db.refresh(company)
        project = models.Project(company_id=company.id, name="p1")
        db.add(project)
        db.commit()
        db.refresh(project)

        response = await client.post(
            "/api/tasks",
            json={
                "title": "API 集成测试",
                "company_id": company.id,
                "project_id": project.id,
                "due_at": "2026-08-15",
                "remind_rule": "before_1m",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["due_at"] == "2026-08-15"
        assert body["remind_start_at"] == "2026-07-15"
        assert "remind_rule" not in body

    async def test_create_task_custom_via_api(
        self, client, make_company, make_project, db
    ):
        from app import models

        company = models.Company(name="custom_compat_2")
        db.add(company)
        db.commit()
        db.refresh(company)
        project = models.Project(company_id=company.id, name="p2")
        db.add(project)
        db.commit()
        db.refresh(project)

        response = await client.post(
            "/api/tasks",
            json={
                "title": "custom API",
                "company_id": company.id,
                "project_id": project.id,
                "due_at": "2026-08-15",
                "remind_rule": "custom",
                "custom_remind_start_at": "2026-08-10",
            },
        )
        assert response.status_code == 201
        assert response.json()["remind_start_at"] == "2026-08-10"

    async def test_create_task_leap_clamp_via_api(
        self, client, make_company, make_project, db
    ):
        from app import models

        company = models.Company(name="custom_compat_3")
        db.add(company)
        db.commit()
        db.refresh(company)
        project = models.Project(company_id=company.id, name="p3")
        db.add(project)
        db.commit()
        db.refresh(project)

        # 2024-03-31 - 1 月 → 2024-02-29
        response = await client.post(
            "/api/tasks",
            json={
                "title": "leap clamp",
                "company_id": company.id,
                "project_id": project.id,
                "due_at": "2024-03-31",
                "remind_rule": "before_1m",
            },
        )
        assert response.status_code == 201
        assert response.json()["remind_start_at"] == "2024-02-29"

    async def test_create_task_response_omits_remind_rule(
        self, client, make_company, make_project, db
    ):
        from app import models

        company = models.Company(name="custom_compat_4")
        db.add(company)
        db.commit()
        db.refresh(company)
        project = models.Project(company_id=company.id, name="p4")
        db.add(project)
        db.commit()
        db.refresh(project)

        response = await client.post(
            "/api/tasks",
            json={
                "title": "no leak",
                "company_id": company.id,
                "project_id": project.id,
                "due_at": "2026-08-15",
                "remind_rule": "before_1w",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert "remind_rule" not in body
        assert body["remind_start_at"] == "2026-08-08"
