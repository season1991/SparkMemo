/**
 * 透视查询 API（v0.5.9）：对接后端 /api/pivot-query 路由。
 *
 * 调用 `POST /api/pivot-query`，请求体为 `PivotQueryRequest`，
 * 响应为 `PivotQueryResponse`（含 period_columns / row_groups / total_rows / version_dates / date_granularity）。
 *
 * 入参约定（与 backend/app/schemas.py PivotQueryRequest 严格对齐）：
 * - pivot_type: 'demand' | 'demand_plus_supply'（v0.5.6 固定 'demand'）
 * - vendor / item / sub_item: 必填，字符串
 * - version_dates: 必填，1-20 个 YYYY-MM-DD
 * - countries / categories / config_codes / config_names: 可选，严格级联
 * - years / months / weeks: 可选，至少传一个；级联
 * - expand_to_daily: bool（默认 false 按周，true 按日）
 * - query_diff: bool = true（v0.5.9 新增；仅 `pivot_type='demand'` 生效；多版本时若某
 *   period_date 各版本 quantity 全等则该日期从 `period_columns` / 各 `quantities`
 *   中剪除；`len(version_dates) <= 1` 由后端内部 no-op）
 *
 * 错误处理：抛 ApiError（client.js 拦截器）。
 */

import client from './client.js'

/**
 * 执行透视查询。
 *
 * @param {object} req PivotQueryRequest
 * @returns {Promise<{
 *   period_columns: string[],
 *   row_groups: Array<{
 *     country: string|null, category: string|null, config_code: string|null,
 *     config_name: string|null, data_type: string|null, ttl: number|null,
 *     version_date: string, quantities: Record<string, number>
 *   }>,
 *   total_rows: number,
 *   version_dates: string[],
 *   date_granularity: 'week' | 'day'
 * }>}
 */
export function queryPivot(req) {
  return client.post('/pivot-query', req)
}


// ==================== v0.5.8 Excel 导出 ====================


/**
 * 透视查询结果导出 .xlsx（v0.5.8 新增；v0.5.9 同步 query_diff）。
 *
 * Body 与 queryPivot 完全相同；后端会再次执行 query_pivot + 笛卡尔积预检 + xlsx 构造。
 * v0.5.9 起 `req.query_diff` 字段也会传递给后端的 `_apply_diff_filter`，
 * 故导出 xlsx 中 sheet 1 的列数与 UI 表格 `period_columns` 1:1 对齐（diff 过滤生效）。
 *
 * @param {object} req PivotQueryRequest（**必须是上次成功查询的请求快照**，否则结果与 UI 展示不一致）
 * @returns {Promise<Blob>} xlsx 二进制（包含 sheet 1「透视结果」+ sheet 2「查询参数快照」）
 */
export function exportPivot(req) {
  return client.post('/pivot-query/export', req, {
    responseType: 'blob',
    timeout: 60000,
  })
}


// ==================== 透视查询辅助 lookup ====================
//
// 这些端点供前端下拉选项使用：
// - countries / categories / config_names：业务行级联数据源（从 dsp_upload_rows 去重）
// - weeks-of-month：根据 ISO 年 + 自然月返回周编号 + 周起始日


/**
 * 返回指定 (vendor+item+sub_item+version_dates) 下所有去重 country。
 *
 * @param {{ vendor: string, item: string, sub_item: string, version_dates: string[] }} base
 * @returns {Promise<string[]>}
 */
export function lookupCountries(base) {
  return client.get('/pivot-query/lookups/countries', {
    params: {
      vendor: base.vendor,
      item: base.item,
      sub_item: base.sub_item,
      version_dates: (base.version_dates || []).join(','),
    },
  })
}

/**
 * 返回指定条件下（已选 countries 时再过滤）去重 category。
 *
 * @param {{ vendor: string, item: string, sub_item: string,
 *           version_dates: string[], countries: string[] }} base
 * @returns {Promise<string[]>}
 */
export function lookupCategories(base) {
  return client.get('/pivot-query/lookups/categories', {
    params: {
      vendor: base.vendor,
      item: base.item,
      sub_item: base.sub_item,
      version_dates: (base.version_dates || []).join(','),
      countries: (base.countries || []).join(','),
    },
  })
}

/**
 * 返回指定条件下（已选 countries + categories 时再过滤）去重 config_name。
 *
 * @param {{ vendor: string, item: string, sub_item: string,
 *           version_dates: string[], countries: string[],
 *           categories: string[] }} base
 * @returns {Promise<string[]>}
 */
export function lookupConfigNames(base) {
  return client.get('/pivot-query/lookups/config-names', {
    params: {
      vendor: base.vendor,
      item: base.item,
      sub_item: base.sub_item,
      version_dates: (base.version_dates || []).join(','),
      countries: (base.countries || []).join(','),
      categories: (base.categories || []).join(','),
    },
  })
}

/**
 * 返回指定 ISO 年 + 自然月的所有 (week_id, week_start_date)。
 *
 * @param {number} year ISO 年
 * @param {number} month 自然月 1-12
 * @returns {Promise<Array<{ week_id: number, week_start_date: string }>>}
 */
export function lookupWeeksOfMonth(year, month) {
  return client.get('/pivot-query/lookups/weeks-of-month', {
    params: { year, month },
  })
}
