/**
 * 邮箱配置 store：单行邮箱配置的 state / actions / getters。
 * state 与 OpenAPI EmailConfigRead 字段完全 snake_case 直存；UI 字段（loading / saving / error）独立维护。
 *
 * 关键约定：
 * 1. fetch() / save() 不抛异常到调用方；调用方通过 store.error / 返回值判断；
 * 2. save() 成功时用响应替换 config（让 exists / id / created_at / updated_at 由后端决定）；
 * 3. 密码字段不出现在 store（store 不持有 smtp_password 明文，遵循后端「响应不回明文」语义）。
 */
import { defineStore } from 'pinia'
import { ApiError } from '../api/client.js'
import { getEmailConfig, saveEmailConfig } from '../api/email_config.js'

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
  created_at: null,
  updated_at: null
})

export const useEmailConfigStore = defineStore('emailConfig', {
  state: () => ({
    config: { ...EMPTY_CONFIG },
    loading: false,
    saving: false,
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
     * 成功：用响应替换 config（关键：让 created_at / updated_at 等元信息刷新）。
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

    /** 清空 config 到初始空壳（一般用于路由切换前的清理，本模块暂未调用）。 */
    clear() {
      this.config = { ...EMPTY_CONFIG }
      this.error = null
      this.loading = false
      this.saving = false
    }
  }
})