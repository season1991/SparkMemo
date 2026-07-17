/**
 * 提醒规则工具（与后端 app/services/reminders.py 对应）。
 *
 * 字段定义见 backend/spec/task_management.md §"remind_rule 翻译规则"。
 * 该模块是纯 JS 函数，没有外部依赖，便于表单 / store / 测试共用。
 */

/** remind_rule 枚举值（与后端 RemindRule Literal 一致） */
export const REMIND_RULE_VALUES = Object.freeze([
  'on_due',
  'before_1d',
  'before_2d',
  'before_3d',
  'before_1w',
  'before_1m',
  'custom'
])

/** select 选项；label 为中文 UI 文案，value 为后端枚举值 */
export const REMIND_RULE_OPTIONS = Object.freeze([
  { value: 'on_due', label: '当天', offsetDays: 0 },
  { value: 'before_1d', label: '提前 1 天', offsetDays: 1 },
  { value: 'before_2d', label: '提前 2 天', offsetDays: 2 },
  { value: 'before_3d', label: '提前 3 天', offsetDays: 3 },
  { value: 'before_1w', label: '提前 1 周', offsetDays: 7 },
  { value: 'before_1m', label: '提前 1 个月', offsetDays: null /* 月历 */ },
  { value: 'custom', label: '特定', offsetDays: null }
])

/** 默认规则（UI 默认值） */
export const DEFAULT_REMIND_RULE = 'on_due'

/**
 * 给定 (due_at, remind_rule)，求出应该存到数据库的 remind_start_at（YYYY-MM-DD）。
 *
 * 注意：本函数仅作 UI 预填/校验，最终入库由后端 resolve_remind_start_at 权威决定。
 * @returns {string|null} 翻译结果；非法入参返回 null
 */
export function previewRemindStartAt(due_at, remind_rule, custom_remind_start_at) {
  if (!due_at || !remind_rule) return null
  if (remind_rule === 'custom') {
    if (!custom_remind_start_at) return null
    return custom_remind_start_at <= due_at ? custom_remind_start_at : null
  }
  if (remind_rule === 'on_due') return due_at
  const offset = offsetByRule(remind_rule)
  if (offset == null) {
    // before_1m 走月历
    if (remind_rule === 'before_1m') return shiftMonthStr(due_at, -1)
    return null
  }
  return shiftDayStr(due_at, -offset)
}

/** 从规则取 offset 天数（custom / before_1m 返回 null） */
function offsetByRule(rule) {
  const found = REMIND_RULE_OPTIONS.find((o) => o.value === rule)
  return found ? found.offsetDays : null
}

/** YYYY-MM-DD 减 N 天，返回同格式字符串 */
export function shiftDayStr(yyyy_mm_dd, deltaDays) {
  const [y, m, d] = yyyy_mm_dd.split('-').map(Number)
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return null
  const dt = new Date(y, m - 1, d)
  dt.setDate(dt.getDate() + deltaDays)
  return fmtDate(dt)
}

/** YYYY-MM-DD 减 N 月，月末 clamp（同后端 shift_month 语义） */
export function shiftMonthStr(yyyy_mm_dd, months) {
  const [y, m, d] = yyyy_mm_dd.split('-').map(Number)
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return null
  let ny = y
  let nm = m + months
  while (nm <= 0) {
    nm += 12
    ny -= 1
  }
  while (nm > 12) {
    nm -= 12
    ny += 1
  }
  // 目标月最后一天：下月 1 日 - 1 day
  const nextMonthFirst = nm === 12 ? new Date(ny + 1, 0, 1) : new Date(ny, nm, 1)
  const lastDay = new Date(nextMonthFirst.getTime() - 24 * 60 * 60 * 1000).getDate()
  return fmtDate(new Date(ny, nm - 1, Math.min(d, lastDay)))
}

function fmtDate(dt) {
  const y = dt.getFullYear()
  const mo = String(dt.getMonth() + 1).padStart(2, '0')
  const da = String(dt.getDate()).padStart(2, '0')
  return `${y}-${mo}-${da}`
}

/**
 * 反推 remind_rule：与后端 infer_remind_rule 镜像。
 * 精确匹配 7 档之一；不匹配则返回 'custom'。
 */
export function inferRemindRule(due_at, remind_start_at) {
  if (!due_at || !remind_start_at) return 'custom'
  if (due_at === remind_start_at) return 'on_due'

  // before_1d / before_2d / before_3d / before_1w
  const deltaDays = dayDelta(due_at, remind_start_at)
  if (deltaDays === 1) return 'before_1d'
  if (deltaDays === 2) return 'before_2d'
  if (deltaDays === 3) return 'before_3d'
  if (deltaDays === 7) return 'before_1w'

  // before_1m：remind_start_at + 1 月 == due_at
  if (deltaDays > 0 && shiftMonthStr(remind_start_at, 1) === due_at) {
    return 'before_1m'
  }

  return 'custom'
}

function dayDelta(future, past) {
  const [y1, m1, d1] = future.split('-').map(Number)
  const [y2, m2, d2] = past.split('-').map(Number)
  if ([y1, m1, d1, y2, m2, d2].some((v) => !Number.isFinite(v))) return -1
  const a = new Date(y1, m1 - 1, d1)
  const b = new Date(y2, m2 - 1, d2)
  return Math.round((a - b) / 86400000)
}

/** 前端表单校验：custom 模式 custom_remind_start_at 必须 <= due_at。 */
export function validateCustom(due_at, remind_rule, custom_remind_start_at) {
  if (remind_rule !== 'custom') return null
  if (!custom_remind_start_at) return '请选择特定提醒日期'
  if (custom_remind_start_at > due_at) return '开始提醒日期晚于截止日'
  return null
}
