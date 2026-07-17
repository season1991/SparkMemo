/**
 * 邮箱配置 store：单行邮箱配置的 state / actions / getters。
 * state 与 OpenAPI EmailConfigRead 字段完全 snake_case 直存；UI 字段（loading / saving / testing / error）独立维护。
 *
 * 关键约定：
 * 1. fetch() / save() / sendTest() 不抛异常到调用方；调用方通过 store.error / 返回值判断；
 * 2. save() / sendTest() 成功时用响应替换 config（让 exists / id / created_at / updated_at / send_time / active 由后端决定）；
 * 3. 密码字段不出现在 store（store 不持有 smtp_password 明文，遵循后端「响应不回明文」语义）；
 * 4. testing 状态与 saving 互斥：同一时刻只允许一个进行中的写操作（详见 spec §2.8 按钮状态表）。
 */
import { defineStore } from 'pinia'
import { ApiError } from '../api/client.js'
import { getEmailConfig, saveEmailConfig, sendTestEmail } from '../api/email_config.js'

const EMPTY_CONFIG = Object.freeze({
  exists: false,
  id: null,
  smtp_host: null,
  smtp_port: null,
  smtp_user: null,
  smtp_password_set: false,
  use_tls: false,
  sender_email: null,
  sender_name: null,
  recipient_email: null,
  recipient_name: null,
  send_time: '08:00',
  active: false,
  created_at: null,
  updated_at: null
})

export const useEmailConfigStore = defineStore('emailConfig', {
  state: () => ({
    config: { ...EMPTY_CONFIG },
    loading: false,
    saving: false,
    testing: false,
    error: null
  }),
  getters: {
    /** 是否已配置（行存在）；用于决定底部元信息是否渲染。 */
    isConfigured: (state) => state.config.exists === true,
    /** 密码是否已设置（仅 GET 响应字段）；用于决定密码框 placeholder。 */
    passwordIsSet: (state) => state.config.smtp_password_set === true,
    /** 是否有旧数据可用于「加载失败但保留旧数据」场景。 */
    hasLoadedData: (state) => state.config.exists === true && state.config.id !== null
  },
  actions: {
    /**
     * 拉取当前邮箱配置；失败时写入 error，但保留旧 config（避免 empty stare）。
     */
    async fetch() {
      this.loading = true
      this.error = null
      try {
        const res = await getEmailConfig()
        this.config = { ...EMPTY_CONFIG, ...res }
      } catch (err) {
        this.error = (err && err.message) || '加载失败'
        // 保留旧 config，由 UI 决定渲染哪个三态
      } finally {
        this.loading = false
      }
    },

    /**
     * 保存邮箱配置（upsert）。
     * payload 字段命名与 OpenAPI EmailConfigWrite 对齐：
     * - smtp_password 为空字符串 / null 时由后端「保留旧值」
     * - recipient_name 为空字符串时转换为 null
     * - send_time / active 每次 PUT 显式覆盖（与 smtp_password 留空保留语义不同）
     * 成功：用响应替换 config（关键：让 created_at / updated_at / send_time / active 等元信息刷新）。
     * 失败：返回 { ok: false, error: ApiError }，调用方根据 status 决定 toast / 字段红字。
     */
    async save(payload) {
      this.saving = true
      this.error = null
      try {
        const res = await saveEmailConfig(payload)
        this.config = { ...EMPTY_CONFIG, ...res }
        return { ok: true }
      } catch (err) {
        if (err instanceof ApiError) {
          this.error = err.message
        } else {
          this.error = (err && err.message) || '保存失败'
        }
        return { ok: false, error: err }
      } finally {
        this.saving = false
      }
    },

    /**
     * 测试发送：调用 POST /api/email/send-test。
     * payload 与 EmailConfigWrite 同结构（snake_case，含 smtp_password 明文 + send_time / active）。
     * 后端会自动 upsert 配置再发送；成功后用响应替换 config（含最新 send_time / active / 元信息）。
     * 不受 active 开关约束：active=false 也允许调用。
     * 失败：返回 { ok: false, error: ApiError }；调用方按 status 决定 toast / 字段红字。
     */
    async sendTest(payload) {
      this.testing = true
      this.error = null
      try {
        const res = await sendTestEmail(payload)
        // 后端响应非 EmailConfigRead 标准结构（仅 {ok, sent_at, recipient}），
        // 但成功路径上 config 不需要刷新（PUT 已由后端自动完成，UI 也可不 reload）。
        // 为保持 state 与 server 一致，发起一次轻量 GET 刷新（失败也不影响 toast）。
        try {
          const fresh = await getEmailConfig()
          this.config = { ...EMPTY_CONFIG, ...fresh }
        } catch {
          // GET 失败不影响测试发送成功状态
        }
        return { ok: true, response: res }
      } catch (err) {
        if (err instanceof ApiError) {
          this.error = err.message
        } else {
          this.error = (err && err.message) || '发送失败'
        }
        return { ok: false, error: err }
      } finally {
        this.testing = false
      }
    },

    /** 清空 config 到初始空壳（一般用于路由切换前的清理，本模块暂未调用）。 */
    clear() {
      this.config = { ...EMPTY_CONFIG }
      this.error = null
      this.loading = false
      this.saving = false
      this.testing = false
    }
  }
})