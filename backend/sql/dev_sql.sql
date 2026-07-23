-- ============================================================================
-- dev_sql.sql
--
-- 用途：SparkMemo 项目所有手工建表 DDL 的单一汇总点。
-- 规约：
--   1. 所有 DDL 必须是 `CREATE TABLE IF NOT EXISTS`，幂等；可重复执行。
--   2. 新增列走 ALTER（参考既有 `_ensure_email_config_columns` 风格）。
--   3. 本文件**不**被 app lifespan 自动调起，仅供运维手动执行。
--   4. 测试环境（SQLite）走 `tests/conftest.py` 的 `Base.metadata.create_all(engine)` 兜底，
--      与生产 MySQL 完全解耦。
--
-- 执行：mysql -u <user> sparkmemo < dev_sql.sql
--       或 pymysql / 其他客户端逐段执行（CREATE TABLE 自身就是 statement 边界）。
--
-- 说明：本文件以「模块 + 版本」为单位分块。后续新增模块 / 老模块 backfill 都往下追加。
-- 严禁拆分到多个 .sql 文件（项目级硬约束，见 spec/README.md §3.8）。
-- ============================================================================


-- ============================================================================
-- v0.6.0 跨表数据填充模块（Cross-Table Fill / CTF）
-- 表清单：cross_table_fill_jobs / cross_table_fill_rows / cross_table_fill_configs
-- 对应 ORM：app/models.py::CrossTableFillJob / Row / Config
-- 关系图：
--   jobs (1) ──< rows (N)        via rows.job_id FK ON DELETE CASCADE
--   jobs (1) ──< configs (0..1)  via configs.job_id FK ON DELETE CASCADE（configs.job_id 是 PK）
-- ============================================================================

CREATE TABLE IF NOT EXISTS `cross_table_fill_jobs` (
  `id`                INT NOT NULL AUTO_INCREMENT                          COMMENT '主键，自增',
  `target_filename`   VARCHAR(256)  NOT NULL                              COMMENT '原 target xlsx 文件名',
  `base_filename`     VARCHAR(256)  NOT NULL                              COMMENT '原 base xlsx 文件名',
  `target_headers`    VARCHAR(2000) NOT NULL                              COMMENT 'JSON 字符串：target 表头',
  `base_headers`      VARCHAR(2000) NOT NULL                              COMMENT 'JSON 字符串：base 表头',
  `target_row_count`  INT           NOT NULL                              COMMENT 'target 数据行数',
  `base_row_count`    INT           NOT NULL                              COMMENT 'base 数据行数',
  `status`            VARCHAR(16)   NOT NULL DEFAULT 'pending'             COMMENT 'pending/configured/executed/failed/expired',
  `result_row_count`  INT           NULL                                  COMMENT 'execute 后：结果行数',
  `filled_count`      INT           NULL                                  COMMENT 'execute 后：≥1 mapping 填充命中的行数',
  `unmatched_count`   INT           NULL                                  COMMENT 'execute 后：base 缺该 key 的行数',
  `multi_match_count` INT           NULL                                  COMMENT 'execute 后：主键命中 base ≥2 行的行数',
  `created_at`        VARCHAR(10)   NOT NULL                              COMMENT 'YYYY-MM-DD',
  `updated_at`        VARCHAR(10)   NOT NULL                              COMMENT 'YYYY-MM-DD',
  `expires_at`        VARCHAR(10)   NOT NULL                              COMMENT 'YYYY-MM-DD，created_at + 24h（可配）',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='跨表数据填充任务元数据表';

CREATE TABLE IF NOT EXISTS `cross_table_fill_rows` (
  `id`         INT          NOT NULL AUTO_INCREMENT                       COMMENT '主键，自增',
  `job_id`     INT          NOT NULL                                     COMMENT 'FK → cross_table_fill_jobs.id',
  `role`       VARCHAR(16)  NOT NULL                                     COMMENT '"target" / "base"；role 字段单表统一存',
  `row_index`  INT          NOT NULL                                     COMMENT '0-based，原 Excel 数据行号（不含表头）',
  `key_value`  VARCHAR(1024) NULL                                        COMMENT 'execute 阶段归一化后的主键拼接',
  `data`       VARCHAR(8192) NOT NULL                                    COMMENT 'JSON 字符串：整行字段值字典',
  PRIMARY KEY (`id`),
  KEY `idx_ctf_rows_job`  (`job_id`),
  KEY `idx_ctf_rows_role` (`role`),
  CONSTRAINT `fk_ctf_rows_job`
    FOREIGN KEY (`job_id`) REFERENCES `cross_table_fill_jobs` (`id`)
    ON DELETE CASCADE
    ON UPDATE NO ACTION
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='跨表数据填充行明细表（target/base 统一存）';

CREATE TABLE IF NOT EXISTS `cross_table_fill_configs` (
  `job_id`         INT          NOT NULL                                COMMENT 'PK & FK → cross_table_fill_jobs.id',
  `target_keys`    VARCHAR(512)  NOT NULL                                COMMENT 'JSON 字符串：target 主键字段名列表',
  `base_keys`      VARCHAR(512)  NOT NULL                                COMMENT 'JSON 字符串：base 主键字段名列表（与 target_keys 等长按位置对应）',
  `mappings`       VARCHAR(8192) NOT NULL                                COMMENT 'JSON 字符串：[{base_field, target_field, mode}]',
  `join_mode`      VARCHAR(16)   NOT NULL DEFAULT 'left'                  COMMENT '"left" / "inner"',
  `match_mode`     VARCHAR(16)   NOT NULL DEFAULT 'merge_multi'           COMMENT '"merge_multi" / "first" / "last"',
  `case_sensitive` TINYINT(1)    NOT NULL DEFAULT 1                       COMMENT 'SQLAlchemy Boolean → TINYINT(1)；True=1，False=0',
  `trim_strings`   TINYINT(1)    NOT NULL DEFAULT 1                       COMMENT '同上',
  `confirm_token`  VARCHAR(64)   NULL                                    COMMENT 'overwrite 模式下的二次确认 UUID；纯 new_column 时 NULL',
  `created_at`     VARCHAR(10)   NOT NULL                                COMMENT 'YYYY-MM-DD',
  `updated_at`     VARCHAR(10)   NOT NULL                                COMMENT 'YYYY-MM-DD',
  PRIMARY KEY (`job_id`),
  CONSTRAINT `fk_ctf_configs_job`
    FOREIGN KEY (`job_id`) REFERENCES `cross_table_fill_jobs` (`id`)
    ON DELETE CASCADE
    ON UPDATE NO ACTION
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='跨表数据填充匹配配置表（一对一 job）';


-- ============================================================================
-- 预留区域：未来模块 / 老模块 backfill 追加此处
-- ============================================================================
