# 跨表数据填充模块规格（前端，v0.6.0）

> 适配 OpenAPI：[../../backend/openapi/cross_table_fill.json](../../backend/openapi/cross_table_fill.json)（`info.version = 0.6.0`，路径 `/api/cross-table-fill/*`；schema `CrossTableFillUploadResponse` / `CrossTableFillJobRead` / `CrossTableFillConfigDigest` / `CrossTableFillConfigRequest` / `CrossTableFillConfigResponse` / `CrossTableFillExecuteResponse` / `CrossTableFillExecuteSummary`）
> 适配后端 spec：[../../backend/spec/cross_table_fill.md](../../backend/spec/cross_table_fill.md)（v0.6.0，含 4 步工作流 + 7 端点 + left-join + merge_multi + overwrite/new_column 双模式）
> 前端实现版本：v0.6.0
> 页面入口：
> - 单页：`views/CrossTableFill.vue`（路由 `/cross-table-fill`；4 步向导式，单 page 全流程），与 PivotQuery 同级（无 hub 页）
> 全局规则遵循 [./README.md](./README.md)；本文档只描述本模块特有的页面拆解、功能点交互、组件契约与测试案例。

> **v0.6.0 前端侧变更**（摘要）：
> 1. **新增顶层模块「跨表数据填充」**：左侧导航第 6 项（HTML 转 Excel 之前）；icon `Connection`（来自 `@element-plus/icons-vue`，语义贴合「两表互联」）。
> 2. **4 步向导式单页 UI**（区别于周需求管理的 hub + 子页面布局）：idle → uploaded → configured → executed 四态切换，每态渲染独立 card；上一步/下一步切换；不允许跨大步跳。
> 3. **三张表的设计完全交给后端**：前端只持 headers + row_count（无数据缓存），避免 10 万行 Excel 进前端卡顿；execute 后只取前 1000 行 preview，完整 xlsx 走 download_token 流式下载（5 min TTL）。
> 4. **`overwrite` 强制二次确认**：mapping 含 `mode='overwrite'` 时前端先 `ElMessageBox.confirm`，确认后自动生成 UUIDv4 作为 `confirm_token` 一并提交；纯 `new_column` 时 `confirm_token=null`（多传也会被后端 409 拦）。
> 5. **`merge_multi` 的多匹配高亮**：preview 中被标记 `multi_match_count` 的行（target 行主键命中 base 多次）打橙色 `el-tag`「主键在 base 命中 N 次，已合并」。
> 6. **测试计划**：API 层 6 用例（upload / getConfig / execute / download / delete）+ View 层 18 用例（4 步骤 + 错误 + 警告 + 二次确认）；vitest run 全过。

---

## 1. 整体页面结构拆解

### 1.1 路由与视图（v0.6.0）

| 路径 | 视图 | 侧边栏激活项 | `meta.title` | 说明 |
|------|------|------------|--------------|------|
| `/cross-table-fill` | `views/CrossTableFill.vue` | 跨表数据填充 | 跨表数据填充 | 单页 4 步向导：上传 → 配置 → 执行 → 结果 |

> **为何单页而非 hub + 子页面**：周需求管理有 3 个互不耦合的子功能（DSP 上传 / 查询 / 删除），故用 hub 导航；本模块是单一线性 ETL 流程，4 步共享 job_id 单例状态，强行拆子页会让用户跨页时丢失选中的字段 / 映射。故单页 + stepper 是更好的选择。

### 1.2 侧边栏（v0.6.0 新增第 6 项）

| 顺序 | 名称 | icon | to |
|------|------|------|----|
| 1 | 今日概述 | `DataAnalysis` | `/` |
| 2 | 任务管理 | `List` | `/tasks` |
| 3 | 周需求管理 | `Upload` | `/dsp-uploads` |
| 4 | 邮箱配置 | `Message` | `/email-config` |
| 5 | HTML 转 Excel | `Document` | `/html-to-excel` |
| 6 | **跨表数据填充**（v0.6.0 新增） | `Connection` | `/cross-table-fill` |

> 图标 `Connection` 来自 `@element-plus/icons-vue`，按需 import。
> 注意：本模块插入到「HTML 转 Excel」**之前**（自然过渡：HTML 转 Excel 是数据加工，本模块是数据加工后的跨表对齐）。

### 1.3 主页 DOM 结构（v0.6.0）

布局遵循 [README §5.2](./README.md#52-布局)：左 220px 导航 + 右侧 56px 页面页头 + 主内容区。

```
<AppLayout>
  <AppSidebar>          ← 220px（第 6 项：跨表数据填充，新激活态）
  <AppPage>
    <AppHeader>
      └─ 左：<h1>{{ route.meta.title }}</h1>  ← "跨表数据填充"
    </AppHeader>
    <AppMain>
      <CrossTableFillView>   ← max-width 960px
        <h2 class="page-title">跨表数据填充</h2>
        <p class="page-hint">上传两张 Excel → 选定主键 → 勾选要填充的字段 → 预览并下载结果</p>

        ┌─ 步骤条 ─────────────────────────────────────────────┐
        │ <el-steps :active="store.stepIndex" finish-status="success"> │
        │   <el-step title="上传两张表" />                     │
        │   <el-step title="配置主键与映射" />                  │
        │   <el-step title="试运行" />                         │
        │   <el-step title="查看结果" />                       │
        │ </el-steps>                                          │
        └────────────────────────────────────────────────────────┘

        <!-- stepIndex === 0：上传卡 -->
        ┌─ 第 1 步：上传两张表（v-if="store.step === 'idle'"）─
        │ <el-card shadow="never" class="step-card">
        │   <el-form>
        │     <el-form-item label="目标表 xlsx（待填充）">
        │       <el-upload :auto-upload="false"
        │                   :on-change="onTargetFileChange"
        │                   :limit="1"
        │                   accept=".xlsx">
        │         <el-button :icon="UploadIcon">选择文件</el-button>
        │       </el-upload>
        │       <span v-if="store.targetFile">{{ store.targetFile.name }}</span>
        │     </el-form-item>
        │     <el-form-item label="基础表 xlsx（数据源）">
        │       <el-upload :auto-upload="false"
        │                   :on-change="onBaseFileChange"
        │                   :limit="1"
        │                   accept=".xlsx">
        │         <el-button :icon="UploadIcon">选择文件</el-button>
        │       </el-upload>
        │       <span v-if="store.baseFile">{{ store.baseFile.name }}</span>
        │     </el-form-item>
        │     <el-form-item label="过期时间（小时）">
        │       <el-input-number v-model="store.expiresInHours"
        │                         :min="1" :max="168" />
        │       <span class="form-hint">默认 24 小时，最长 168 小时（7 天）</span>
        │     </el-form-item>
        │     <div class="form-actions">
        │       <el-button @click="onReset">重置</el-button>
        │       <el-button type="primary"
        │                   :icon="Promotion"
        │                   :loading="store.uploading"
        │                   :disabled="!store.canUpload"
        │                   @click="onUpload">开始解析</el-button>
        │     </div>
        │   </el-form>
        │ </el-card>
        └────────────────────────────────────────────────────────┘

        <!-- stepIndex === 1：表结构 + 主键 + 映射配置 -->
        ┌─ 第 2 步：配置（v-if="store.step === 'uploaded'"）────
        │ <el-card shadow="never" class="step-card">
        │   <h3>目标表 <el-tag>{{ store.uploadResult.target_filename }}</el-tag></h3>
        │   <el-table :data="targetHeaderRows" stripe size="small">
        │     <el-table-column label="字段名" prop="name" />
        │   </el-table>
        │   <p class="meta-info">共 {{ store.uploadResult.target_row_count }} 行</p>
        │
        │   <h3>基础表 <el-tag>{{ store.uploadResult.base_filename }}</el-tag></h3>
        │   <el-table :data="baseHeaderRows" stripe size="small">
        │     <el-table-column label="字段名" prop="name" />
        │   </el-table>
        │   <p class="meta-info">共 {{ store.uploadResult.base_row_count }} 行</p>
        │
        │   <el-divider />
        │
        │   <h3>主键字段（target_keys 与 base_keys 一一对应）</h3>
        │   <div v-for="(tk, idx) in store.targetKeys" :key="idx" class="key-pair-row">
        │     <el-select v-model="store.targetKeys[idx]"
        │                :options="store.uploadResult.target_headers.map(h => ({value:h,label:h}))"
        │                placeholder="目标表字段" />
        │     <span class="key-separator">⟷</span>
        │     <el-select v-model="store.baseKeys[idx]"
        │                :options="store.uploadResult.base_headers.map(h => ({value:h,label:h}))"
        │                placeholder="基础表字段" />
        │     <el-button v-if="idx === store.targetKeys.length - 1"
        │                size="small"
        │                :icon="Plus"
        │                @click="addKeyPair">新增一对</el-button>
        │     <el-button v-if="store.targetKeys.length > 1"
        │                size="small"
        │                :icon="Minus"
        │                @click="removeKeyPair(idx)">移除</el-button>
        │   </div>
        │
        │   <el-divider />
        │
        │   <h3>映射规则（基础表 → 目标表）</h3>
        │   <el-table :data="store.mappings" stripe size="small">
        │     <el-table-column label="基础表字段" prop="base_field">
        │       <template #default="{ row }">
        │         <el-select v-model="row.base_field"
        │                    :options="store.uploadResult.base_headers.map(h => ({value:h,label:h}))" />
        │       </template>
        │     </el-table-column>
        │     <el-table-column label="目标列" prop="target_field">
        │       <template #default="{ row }">
        │         <el-select v-model="row.target_field"
        │                    :options="store.uploadResult.target_headers.map(h => ({value:h,label:h}))" />
        │       </template>
        │     </el-table-column>
        │     <el-table-column label="模式" prop="mode" width="180">
        │       <template #default="{ row }">
        │         <el-radio-group v-model="row.mode">
        │           <el-radio-button value="new_column">新增列</el-radio-button>
        │           <el-radio-button value="overwrite">覆盖原列</el-radio-button>
        │         </el-radio-group>
        │       </template>
        │     </el-table-column>
        │     <el-table-column label="操作" width="100">
        │       <template #default="{ $index }">
        │         <el-button size="small" type="danger" :icon="Delete"
        │                    @click="removeMapping($index)">删除</el-button>
        │       </template>
        │     </el-table-column>
        │   </el-table>
        │   <el-button :icon="Plus" @click="addMapping">新增映射</el-button>
        │
        │   <el-divider />
        │
        │   <h3>高级选项</h3>
        │   <el-form-item label="Join 模式">
        │     <el-radio-group v-model="store.joinMode">
        │       <el-radio value="left">left join（保留全部 target 行；VLOOKUP 默认）</el-radio>
        │       <el-radio value="inner">inner join（只保留命中行）</el-radio>
        │     </el-radio-group>
        │   </el-form-item>
        │   <el-form-item label="多匹配处理">
        │     <el-radio-group v-model="store.matchMode">
        │       <el-radio value="merge_multi">合并多值（用 ; 分隔）</el-radio>
        │       <el-radio value="first">取第一条</el-radio>
        │       <el-radio value="last">取最后一条</el-radio>
        │     </el-radio-group>
        │   </el-form-item>
        │   <el-checkbox v-model="store.caseSensitive">大小写敏感</el-checkbox>
        │   <el-checkbox v-model="store.trimStrings">去除两端空格</el-checkbox>
        │
        │   <div class="form-actions">
        │     <el-button @click="store.goToStep('idle')">上一步</el-button>
        │     <el-button type="primary"
        │                 :icon="Promotion"
        │                 :loading="store.configuring"
        │                 :disabled="!store.canConfigure"
        │                 @click="onConfigure">下一步</el-button>
        │   </div>
        │ </el-card>
        └────────────────────────────────────────────────────────┘

        <!-- stepIndex === 2：试运行 / warnings -->
        ┌─ 第 3 步：试运行（v-if="store.step === 'configured'"）─
        │ <el-card shadow="never" class="step-card">
        │   <h3>配置摘要</h3>
        │   <el-descriptions :column="2" border>
        │     <el-descriptions-item label="主键对">
        │       <span v-for="(tk, i) in store.configDigest.target_keys" :key="i">
        │         <el-tag size="small">{{ tk }} ⟷ {{ store.configDigest.base_keys[i] }}</el-tag>
        │       </span>
        │     </el-descriptions-item>
        │     <el-descriptions-item label="映射条数">
        │       {{ store.configDigest.mapping_count }}
        │     </el-descriptions-item>
        │     <el-descriptions-item label="含 overwrite">
        │       {{ store.configDigest.has_overwrite ? '是' : '否' }}
        │     </el-descriptions-item>
        │     <el-descriptions-item label="含 new_column">
        │       {{ store.configDigest.has_new_column ? '是' : '否' }}
        │     </el-descriptions-item>
        │     <el-descriptions-item label="Join 模式">{{ store.configDigest.join_mode }}</el-descriptions-item>
        │     <el-descriptions-item label="多匹配处理">{{ store.configDigest.match_mode }}</el-descriptions-item>
        │   </el-descriptions>
        │
        │   <el-alert v-for="(w, i) in store.warnings" :key="i"
        │             :title="w" type="warning" :closable="false" show-icon />
        │
        │   <div class="form-actions">
        │     <el-button @click="store.goToStep('uploaded')">上一步（修改配置）</el-button>
        │     <el-button type="primary"
        │                 :icon="VideoPlay"
        │                 :loading="store.executing"
        │                 @click="onExecute">执行填充</el-button>
        │   </div>
        │ </el-card>
        └────────────────────────────────────────────────────────┘

        <!-- stepIndex === 3：结果预览 + 下载 -->
        ┌─ 第 4 步：结果（v-if="store.step === 'executed'"）─────
        │ <el-card shadow="never" class="step-card">
        │   <h3>执行摘要</h3>
        │   <el-descriptions :column="3" border>
        │     <el-descriptions-item label="target 行数">
        │       {{ store.executeResponse.summary.target_row_count }}
        │     </el-descriptions-item>
        │     <el-descriptions-item label="结果行数">
        │       {{ store.executeResponse.summary.result_row_count }}
        │     </el-descriptions-item>
        │     <el-descriptions-item label="填充命中">
        │       {{ store.executeResponse.summary.filled_count }}
        │     </el-descriptions-item>
        │     <el-descriptions-item label="未命中">
        │       {{ store.executeResponse.summary.unmatched_count }}
        │     </el-descriptions-item>
        │     <el-descriptions-item label="多匹配">
        │       {{ store.executeResponse.summary.multi_match_count }}
        │       <el-tag v-if="store.executeResponse.summary.multi_match_count > 0"
        │               type="warning" size="small">合并展示</el-tag>
        │     </el-descriptions-item>
        │   </el-descriptions>
        │
        │   <h3>预览（前 1000 行）</h3>
        │   <el-table :data="store.executeResponse.preview" stripe size="small"
        │             :max-height="400">
        │     <el-table-column v-for="col in store.executeResponse.preview_headers"
        │                       :key="col"
        │                       :prop="col"
        │                       :label="col"
        │                       min-width="120" />
        │   </el-table>
        │   <p v-if="store.executeResponse.summary.result_row_count > 1000"
        │      class="meta-info">
        │     仅展示前 1000 行；完整数据请下载 xlsx 文件
        │   </p>
        │
        │   <div class="form-actions">
        │     <el-button @click="store.goToStep('configured')">上一步</el-button>
        │     <el-button type="success"
        │                 :icon="Download"
        │                 :loading="store.downloading"
        │                 @click="onDownload">下载完整结果 xlsx</el-button>
        │     <el-button type="danger"
        │                 :icon="Delete"
        │                 @click="onCleanUp">清理任务（删除）</el-button>
        │   </div>
        │ </el-card>
        └────────────────────────────────────────────────────────┘

      </CrossTableFillView>
    </AppMain>
  </AppPage>
</AppLayout>
```

### 1.4 模块涉及组件与 store（v0.6.0 全新增）

| 类型 | 名称 | 职责 |
|------|------|------|
| Layout | `layouts/AppLayout.vue` | 整体布局（已存在，仅影响 menu 高亮计算） |
| Layout | `layouts/AppSidebar.vue` | 左导航；**v0.6.0 第 6 项新增**「跨表数据填充」，icon `Connection` |
| View | `views/CrossTableFill.vue` | **新增** 4 步向导单页；管 4 步状态切换 + 表单提交 + 错误展示 |
| Store（共享） | `stores/useCrossTableFillStore.js` | state（targetFile / baseFile / expiresInHours / stepIndex / jobId / uploadResult / targetKeys / baseKeys / mappings / joinMode / matchMode / caseSensitive / trimStrings / configuring / configDigest / configResponse / warnings / executing / executeResponse / downloading / uploading）+ actions（`upload / patchConfig / execute / download / cleanUp / reset / goToStep`）+ getters（`canUpload / canConfigure / step`） |
| API | `api/cross_table_fill.js` | `uploadCrossTable / getCrossTableJob / listCrossTableJobs / patchCrossTableConfig / executeCrossTable / downloadCrossTableResult / deleteCrossTableJob` 7 个函数（对应后端 7 端点） |

### 1.5 新增前端工具链

> 本模块沿用既有工具链，**不新增依赖**：
> - vitest@^2 / @vue/test-utils@^2 / jsdom@^25（与周需求管理共享）
> - Element Plus icon 新增 `Connection`（按需 import，不增加 bundle 体积）

---

## 2. 页面的功能点

### 2.1 功能点：进入跨表填充页

#### 入口
- 浏览器访问 `#/cross-table-fill`；
- 左侧导航条点击「跨表数据填充」→ `router.push('/cross-table-fill')`。

#### 静态展示规则
- 侧边栏第 6 项激活（icon `Connection`）；
- 页面页头：左侧 `meta.title` = `跨表数据填充`；
- 主区：标题 + hint + 步骤条（active=0）+ 上传卡（step=`idle`）。

#### 进入初始态
- `store.step = 'idle'`；`store.stepIndex = 0`
- `store.targetFile = null`；`store.baseFile = null`
- `store.expiresInHours = 24`（默认）
- `store.canUpload === false`（两个文件都未选）

### 2.2 功能点：选择目标表 / 基础表 xlsx

#### 交互逻辑
- 用户分别点击两张「选择文件」按钮 → 触发 `el-upload` 单文件选择器（MIME 限制 `accept=".xlsx"`）；
- 用户选中文件后，`onChange` 触发 `store.setTargetFile(file)` 或 `store.setBaseFile(file)`：

| 阶段 | 内容 |
|------|------|
| 文件大小校验 | 后端 20 MB；前端可在 `onChange` 入口做早期检查 → 超 20 MB → `ElMessage.warning('文件超过 20 MB 上限')` 并清空 |
| 后缀校验 | 前端检查 `.xlsx` → 非 `.xlsx` → `ElMessage.error('仅支持 .xlsx 文件')` 并清空（前端短路，后端也会兜底 422） |
| 写入 store | `targetFile = file` / `baseFile = file`；文件名 chip 显示在按钮右侧（`{{ file.name }}`） |
| 替换文件 | 若已选过，点击新文件 → 直接覆盖旧 file；不需要「先移除再选择」|
| 「开始解析」按钮 enable | 两文件都选齐 + 未上传时 → `canUpload === true` |

#### 文件未选时的显示
- 「目标表 xlsx」按钮 label = `选择文件`；右侧无 chip；
- 「基础表 xlsx」按钮 label = `选择文件`；右侧无 chip。

### 2.3 功能点：开始解析（Step 1 → Step 2）

| 阶段 | 内容 |
|------|------|
| 操作前 | 两文件已选 |
| 触发动作 | 点「开始解析」|
| 前端校验 | `store.canUpload === true`；`expiresInHours` 在 [1, 168]（el-input-number 已限制） |
| 接口请求 | `POST /api/cross-table-fill/jobs` multipart：`target_file` + `base_file` + `expires_in_hours` |
| 成功逻辑（201） | toast「解析成功：目标表 N 行 / 基础表 M 行」；`store.uploadResult = response.body`；`store.step = 'uploaded'`；`store.stepIndex = 1`；自动初始化 `targetKeys` 与 `baseKeys` 为空数组 `[]`（用户后续手动新增） |
| 失败（413） | `ElMessage.error('文件超过 20 MB 上限')`；状态保持 idle |
| 失败（415 / 422） | `showApiError(err)` 走通用 toast |
| 失败（400） | 同上 |
| 失败（网络 / timeout） | `ElMessage.error('网络异常，请稍后重试')` |

> **为何不用 `ElMessageBox.confirm`**：本模块没有「重传 / 替换」语义（不像 dsp_upload 有版本冲突 409）；上传失败仅 toast 即可，重试由用户手动重选文件触发。

### 2.4 功能点：配置主键（Step 2）

#### 主键对 UI（key-pair-row）
- 默认初始为空数组 `[]`；用户首次进入 Step 2 看到「请添加至少一对主键」；
- 点「新增一对」→ 追加一对 `{ targetKey: null, baseKey: null }`；
- 任意一行可点「移除」→ 移除该对（最后一行不可移除，至少保留 1 对）；
- 每对包含两个 `el-select`：左 target 字段下拉，右 base 字段下拉；中间显示 `⟷`；
- 选择器选项来自 `store.uploadResult.target_headers` 与 `store.uploadResult.base_headers`（字符串列表）。

#### 主键校验
- `canConfigure` getter 内必须 `store.targetKeys.length >= 1`；
- 每对的 `targetKey` 与 `baseKey` 都必须非空；
- 两对之间 `targetKey` 不可重复（避免主键冲突）；提示「主键在同一张表内重复：xxx」。

### 2.5 功能点：配置映射（Step 2）

#### 映射表 UI（el-table）
- `store.mappings` 是 `list[{base_field, target_field, mode}]`；
- 默认 1 行：「基础表字段下拉 + 目标列下拉 + 单选按钮组（new_column / overwrite）+ 删除按钮」；
- 点「新增映射」→ 追加一行（同表 1 列）；
- 「删除」→ 从数组移除该行（最后一行可删，因 mappings 至少 1 条由 PATCH 时校验）。

#### mode 切换 UX
- 默认 `new_column`（安全默认）；
- 用户切到 `overwrite` → 立即 `ElMessageBox.confirm`「覆盖模式将覆盖目标表的同名列，确认切换？」，用户选「确定」→ 状态切换、写入 store；选「取消」→ 单选按钮回退 `new_column`；
- 整体 PATCH 时若 `has_overwrite === true` 但 `confirm_token` 为 null → 走 §2.7 二跳确认。

#### 表 / target 列下拉
- 选项均为上传时返回的 headers 列表；
- `target_field` 与现有 target 已有列同名时，下拉选项正常包含该名（这是允许的，因为后端会自动加 `_filled` 后缀；warnings 提示用户）。

### 2.6 功能点：高级选项（Step 2）

| 选项 | 默认 | 说明 |
|------|------|------|
| join_mode | `left` | left join / inner join 单选 |
| match_mode | `merge_multi` | merge_multi / first / last 单选 |
| case_sensitive | `true` | 复选框；取消勾选 → 大小写不敏感 |
| trim_strings | `true` | 复选框；取消勾选 → 不去两端空格 |

> **变更不触发重新上传**：这些是 PATCH payload 的字段，下一点击「下一步」统一提交。

### 2.7 功能点：配置提交（Step 2 → Step 3，含 overwrite 二次确认）

| 阶段 | 内容 |
|------|------|
| 操作前 | 至少 1 对主键 + 至少 1 条 mapping + 所有字段非空 |
| 触发动作 | 点「下一步」|
| 前端校验 | `canConfigure === true`；否则字段级红字 / toast |
| 含 overwrite 时 | `ElMessageBox.confirm('本次配置含「覆盖原列」模式，将覆盖目标表的同名列。如已确认请继续；如需调整请返回修改。', '覆盖确认', { type: 'warning', confirmButtonText: '已确认，继续', cancelButtonText: '返回修改' })`；用户选「返回修改」→ 不发请求；选「已确认，继续」→ 生成 `confirm_token = crypto.randomUUID()`，进入 PATCH |
| 不含 overwrite 时 | `confirm_token = null`，直接 PATCH |
| 接口请求 | `PATCH /api/cross-table-fill/jobs/{job_id}/config` JSON body |
| 成功（200） | `store.configDigest = response.config_digest`；`store.warnings = response.warnings`；`store.step = 'configured'`；`store.stepIndex = 2` |
| 失败 422（字段缺失 / 不等长） | toast 显示后端 detail；状态保留在 Step 2，可修改后重试 |
| 失败 409（overwrite 缺 token / token 校验失败） | 几乎不可能走到（前端已先做 confirm）；若走到 → toast 后端 detail，让用户回 Step 2 重配 |
| 失败 409（job 已 executed / 过期） | toast 后端 detail；保留在 Step 2，重置后重做 |

#### warnings 渲染
- 后端 warnings 是 `list[str]`（纯文本）；
- Step 3 顶部用 `el-alert type="warning"` 渲染（每条一个 alert）；
- 例：「target_keys 在 target 表有 5 个空键值行，运行时将判为 unmatched」；
- 例：「字段 '部门' 与 target 已有列同名，将自动加 _filled 后缀」。

### 2.8 功能点：执行填充（Step 3 → Step 4）

| 阶段 | 内容 |
|------|------|
| 操作前 | status=configured；warnings 已展示 |
| 触发动作 | 点「执行填充」|
| 接口请求 | `POST /api/cross-table-fill/jobs/{job_id}/execute`（无 body）|
| 成功（200） | `store.executeResponse = response`；`store.step = 'executed'`；`store.stepIndex = 3`；token 自动存到 `store.downloadToken`（供「下载完整结果」按钮使用） |
| 失败 404 | toast「任务不存在」；建议用户清理后重来 |
| 失败 409（job expired / 未 configured） | toast 后端 detail；状态回 Step 2 / Step 3 |
| 失败 5xx | `showApiError(err)` |

### 2.9 功能点：查看结果（Step 4）

#### 执行摘要卡（el-descriptions）
- 「target 行数 / 结果行数 / 填充命中 / 未命中 / 多匹配」5 个只读字段；
- 「未命中」> 0 → 加一个 `el-tag type="info"`「有 N 行 base 表缺失该主键」；
- 「多匹配」> 0 → 加一个 `el-tag type="warning"`「合并展示」。

#### 预览表（el-table）
- 列来自 `executeResponse.preview_headers`（顺序保留）；
- 数据来自 `executeResponse.preview`（最多 1000 行）；
- 单元格：
  - 数字 / 字符串直接显示；
  - `null` 显示 `—`（不写 `0`，避免「无」与「0」混淆）；
  - 长度 > 30 字符的字符串自动 ellipsis（`show-overflow-tooltip`）；
- `:max-height="400"` 固定滚动区；
- 行底色不变（spec 未要求）。

#### 「下载完整结果 xlsx」按钮
- 点击触发 `onDownload()`：
  1. `store.downloading = true`；
  2. 调 `downloadCrossTableResult(job_id, download_token)` → `GET /api/cross-table-fill/jobs/{job_id}/download?token=...`，`responseType: 'blob'`，`timeout: 60000`；
  3. 成功 → `downloadBlob(blob, 'cross_table_fill_<id>_filled_<timestamp>.xlsx')`，toast「已开始下载」；
  4. 失败 401（token 过期） → toast「下载链接已失效，请重新执行」；
  5. 失败 5xx → `showApiError(err)`；
  6. `finally: store.downloading = false`。
- 按钮 disabled 当 `downloading === true`；
- token 与 job_id 同时传（后端校验两者匹配）。

#### 「清理任务（删除）」按钮
- 二次确认：`ElMessageBox.confirm('删除该任务将一并清理 rows 与 configs，无法恢复。确认删除？', '清理任务', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })`；
- 用户选「删除」→ 调 `deleteCrossTableJob(job_id)` → 204；
- 成功 → toast「已清理」；`store.cleanUp()` 重置全部 state → `step='idle'`；`stepIndex=0`；
- 失败 → `showApiError(err)`。

### 2.10 功能点：导航（上一步 / 重置）

#### 上一步按钮
- 仅 Step 2/3/4 显示「上一步」；
- 行为仅切 `store.step` 与 `store.stepIndex`；**不丢已经上传的文件或已经配的配置**（store state 持久）；
- Step 2 → Step 1：file 选择重置为空，校验未上传场景；
- Step 3 → Step 2：保留 mappings 与 keys（用于「试运行不通过可改」）；
- Step 4 → Step 3：不抛 state，只把视图切回。

> **设计取舍**：用户若想「重新换两张表」，是回到 Step 1 → 重传文件 → 自动清掉旧 job 上下文；具体行为见 §2.10.1。

#### 重置按钮（Step 1 才有）
- 触发：`ElMessageBox.confirm('重置会清空当前任务、文件选择与所有配置。是否继续？', '重置', { type: 'warning', confirmButtonText: '重置', cancelButtonText: '取消' })`；
- 用户选「重置」→ `store.cleanUp()`；
- 用户选「取消」→ 不动作。

#### 2.10.1 用户换文件的特殊规则
- Step 1 选过文件后想换新文件：直接选即可，el-upload 自带 limit=1 + onChange 重新触发 setTargetFile；
- Step 2 之后想换文件：必须先点「上一步」回 Step 1，否则：当前 store.uploadResult 与新文件不匹配 → UI 错乱；
- 实际上：el-upload 的 limit=1 让用户「再选一次」直接覆盖；store.setTargetFile 不感知已上传；
- 后端每次 upload 都是新 job_id，旧 job 24h 后自动过期；用户无需手动清理。

### 2.11 功能点：错误与异常

| HTTP | 场景 | UI 行为 |
|------|------|---------|
| 400 | 文件 MIME 异常 / 解析 cell 含不支持类型 | `showApiError(err)` |
| 401 | 下载 token 缺失 / 错误 / 过期 | `ElMessage.error('下载链接已失效，请重新执行')` |
| 404 | job_id 不存在 | `showApiError(err)` |
| 409 | job 已 executed / 过期；overwrite 缺 token；new_column-only 多 token | `showApiError(err)` |
| 413 | 任一文件 > 20 MB | `showApiError(err)` |
| 415 | 任一文件 MIME 非 .xlsx | `showApiError(err)` |
| 422 | 工作簿无 sheet / 表头为空 / 表头重复名；mappings 字段缺失；keys 等长校验失败 | `showApiError(err)`（detail 为字符串或 list，前端 humanize 已有） |
| 5xx | 服务异常 | `showApiError(err)`（沿用全局 humanize） |
| 网络 | `ECONNABORTED` / 断网 | `ElMessage.error('网络异常，请稍后重试')` |

> 所有错误统一走 `api/client.js::showApiError(err)`，确保 UI 行为一致。

---

## 3. Store 层设计

### 3.1 `useCrossTableFillStore.js`

```js
/**
 * 跨表数据填充 store（v0.6.0）。
 *
 * state 字段：
 * - stepIndex              : 0..3  当前步骤索引（驱动 el-steps）
 * - targetFile             : File | null
 * - baseFile               : File | null
 * - expiresInHours         : number  默认 24
 * - uploading              : bool
 * - uploadResult           : CrossTableFillUploadResponse | null  解析后的元数据
 * - jobId                  : number | null  upload 后写入
 * - targetKeys             : string[]   与 baseKeys 一一对应；初始 []
 * - baseKeys               : string[]
 * - mappings               : { base_field, target_field, mode }[]
 * - joinMode               : 'left' | 'inner'
 * - matchMode              : 'merge_multi' | 'first' | 'last'
 * - caseSensitive          : bool  默认 true
 * - trimStrings            : bool  默认 true
 * - configuring            : bool
 * - configDigest           : CrossTableFillConfigDigest | null
 * - configResponse         : CrossTableFillConfigResponse | null
 * - warnings               : string[]
 * - executing              : bool
 * - executeResponse        : CrossTableFillExecuteResponse | null
 * - downloadToken          : string  来自 executeResponse.download_token
 * - downloading            : bool
 *
 * getters：
 * - step                   : 'idle' | 'uploaded' | 'configured' | 'executed'  与 stepIndex 双向绑定
 * - canUpload              : targetFile != null && baseFile != null && !uploading
 * - canConfigure           : targetKeys.length >= 1 && baseKeys.length === targetKeys.length &&
 *                            every key 非空 + mappings.length >= 1 &&
 *                            every mapping 的 base_field / target_field 非空
 * - hasOverwriteMapping    : mappings 任意一条 mode === 'overwrite'
 *
 * actions：
 * - setTargetFile(file) / setBaseFile(file)：写 File；前端做 .xlsx / size 短路校验
 * - upload()：multipart POST → uploadResult / jobId / step='uploaded'
 * - addKeyPair() / removeKeyPair(idx)
 * - addMapping() / removeMapping(idx) / updateMapping(idx, patch)
 * - patchConfig(confirmToken?)：PATCH → configResponse / step='configured'
 * - execute()：POST → executeResponse / downloadToken / step='executed'
 * - download()：GET (blob) → downloadBlob → 重置 downloading
 * - cleanUp()：DELETE → 重置全部 state 到 idle（不抛错误；前端兜底）
 * - reset()：本地清空 state（不发请求）
 * - goToStep(targetStep)：仅切 step / stepIndex，不发请求（仅在已上传/已配置时允许向前跳）
 */
```

### 3.2 state 流转图

```
                     (empty)
                        │
                        ▼
              step='idle' / stepIndex=0
                │ targetFile, baseFile
                │ setExpiresInHours
                ▼
              upload() ─────────────► [Step 1 完成]
                │
                ▼
            step='uploaded' / stepIndex=1
                │
                │ addKeyPair, addMapping, setJoinMode 等
                │
                │ patchConfig(confirm_token)
                ▼
            step='configured' / stepIndex=2
                │ warnings + digest 展示
                │
                │ execute()
                ▼
            step='executed' / stepIndex=3
                │ preview + download
                │
                │ cleanUp() 或 reset()
                ▼
            step='idle' (回到初态)

goToStep 仅支持：
  - 'uploaded' → 'idle' (Step 2 上一步)
  - 'configured' → 'uploaded' (Step 3 上一步)
  - 'executed' → 'configured' (Step 4 上一步)
不允许跨越式跳；任何 back 都不丢已有 state。
```

---

## 4. API 层

### 4.1 `api/cross_table_fill.js` 新建

```js
import client from './client.js'

/**
 * 上传两张表（multipart）。
 *
 * @param {{ target: File, base: File, expires_in_hours?: number }} input
 * @returns {Promise<CrossTableFillUploadResponse>}
 */
export function uploadCrossTable({ target, base, expires_in_hours }) {
  const form = new FormData()
  form.append('target_file', target)
  form.append('base_file', base)
  if (expires_in_hours !== undefined) {
    form.append('expires_in_hours', String(expires_in_hours))
  }
  return client.post('/cross-table-fill/jobs', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000
  })
}

/**
 * 单查 job（执行后用于刷新 status 等）。
 */
export function getCrossTableJob(jobId) {
  return client.get(`/cross-table-fill/jobs/${jobId}`)
}

/**
 * 列表（默认按 id 倒序）。
 */
export function listCrossTableJobs(opts = {}) {
  return client.get('/cross-table-fill/jobs', { params: opts })
}

/**
 * PATCH /config：主键 + 映射 + 高级选项。
 *
 * @param {number} jobId
 * @param {{
 *   target_keys: string[],
 *   base_keys: string[],
 *   mappings: { base_field: string, target_field: string, mode: 'overwrite' | 'new_column' }[],
 *   join_mode?: 'left' | 'inner',
 *   match_mode?: 'merge_multi' | 'first' | 'last',
 *   case_sensitive?: boolean,
 *   trim_strings?: boolean,
 *   confirm_token?: string | null,
 * }} payload
 * @returns {Promise<CrossTableFillConfigResponse>}
 */
export function patchCrossTableConfig(jobId, payload) {
  return client.patch(`/cross-table-fill/jobs/${jobId}/config`, payload)
}

/**
 * 执行匹配，返回前 1000 行 preview + download_token。
 *
 * @returns {Promise<CrossTableFillExecuteResponse>}
 */
export function executeCrossTable(jobId) {
  return client.post(`/cross-table-fill/jobs/${jobId}/execute`)
}

/**
 * 下载填充结果 xlsx（流式，responseType='blob'）。
 *
 * @param {number} jobId
 * @param {string} token 来自 executeResponse.download_token
 * @returns {Promise<Blob>}
 */
export function downloadCrossTableResult(jobId, token) {
  return client.get(`/cross-table-fill/jobs/${jobId}/download`, {
    params: { token },
    responseType: 'blob',
    timeout: 60000
  })
}

/**
 * 主动删除 job（级联清 rows / configs）。
 *
 * @returns {Promise<void>}
 */
export function deleteCrossTableJob(jobId) {
  return client.delete(`/cross-table-fill/jobs/${jobId}`)
}
```

> `downloadBlob` 工具函数复用 v0.5.8 已落地的 `utils/downloadBlob.js`，不新增工具。

---

## 5. View 层

### 5.1 `views/CrossTableFill.vue` 单文件

```vue
<script setup>
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Connection,
  Delete,
  Download,
  Minus,
  Plus,
  Promotion,
  Upload,
  VideoPlay,
} from '@element-plus/icons-vue'
import { useCrossTableFillStore } from '../stores/useCrossTableFillStore.js'
import { showApiError } from '../api/client.js'
import { downloadBlob } from '../utils/downloadBlob.js'

const router = useRouter()
const store = useCrossTableFillStore()
const { stepIndex, targetFile, baseFile, uploadResult, mappings, targetKeys, baseKeys } = storeToRefs(store)

// 各步骤的子函数（伪代码；具体 store actions 见 spec §3）
function onTargetFileChange(file) { /* .xlsx & size 校验 → setTargetFile */ }
function onBaseFileChange(file) { /* 同上 */ }
async function onUpload() { /* store.upload() */ }
async function onConfigure() { /* 含 overwrite 二次确认 → store.patchConfig(token) */ }
async function onExecute() { /* store.execute() */ }
async function onDownload() { /* store.download() + downloadBlob */ }
async function onCleanUp() { /* confirm + store.cleanUp() */ }
function onReset() { /* confirm + store.reset() */ }
function addKeyPair() { store.targetKeys.push(''); store.baseKeys.push('') }
function removeKeyPair(idx) { /* store.targetKeys.splice / baseKeys.splice */ }
function addMapping() { store.mappings.push({ base_field: '', target_field: '', mode: 'new_column' }) }
function removeMapping(idx) { store.mappings.splice(idx, 1) }
function onModeChange(row, val) {
  if (val === 'overwrite') {
    ElMessageBox.confirm('覆盖模式将覆盖目标表的同名列，确认切换？', '提示', {
      type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消'
    }).catch(() => {
      row.mode = 'new_column'
    })
  }
}
</script>

<template>
  <div class="cross-table-fill">
    <h2 class="page-title">跨表数据填充</h2>
    <p class="page-hint">上传两张 Excel → 选定主键 → 勾选要填充的字段 → 预览并下载结果</p>

    <el-steps :active="stepIndex" finish-status="success" class="step-indicator">
      <el-step title="上传两张表" />
      <el-step title="配置主键与映射" />
      <el-step title="试运行" />
      <el-step title="查看结果" />
    </el-steps>

    <!-- Step 1 -->
    <el-card v-if="store.step === 'idle'" shadow="never" class="step-card">
      <el-form label-width="160px">
        <el-form-item label="目标表 xlsx">
          <el-upload :auto-upload="false" :on-change="onTargetFileChange" :limit="1" accept=".xlsx">
            <el-button :icon="Upload">选择文件</el-button>
          </el-upload>
          <span v-if="targetFile" class="file-name">{{ targetFile.name }}</span>
        </el-form-item>
        <el-form-item label="基础表 xlsx">
          <el-upload :auto-upload="false" :on-change="onBaseFileChange" :limit="1" accept=".xlsx">
            <el-button :icon="Upload">选择文件</el-button>
          </el-upload>
          <span v-if="baseFile" class="file-name">{{ baseFile.name }}</span>
        </el-form-item>
        <el-form-item label="过期时间（小时）">
          <el-input-number v-model="store.expiresInHours" :min="1" :max="168" />
          <span class="form-hint">默认 24 小时，最长 168 小时（7 天）</span>
        </el-form-item>
        <div class="form-actions">
          <el-button @click="onReset">重置</el-button>
          <el-button type="primary" :icon="Promotion" :loading="store.uploading" :disabled="!store.canUpload" @click="onUpload">
            开始解析
          </el-button>
        </div>
      </el-form>
    </el-card>

    <!-- Step 2: 配置（详见 §1.3 大段 HTML） -->
    <!-- Step 3: 试运行（详见 §1.3） -->
    <!-- Step 4: 结果（详见 §1.3） -->

    <!-- ...按 1.3 完整模板展开... -->
  </div>
</template>

<style scoped>
.cross-table-fill {
  max-width: 960px;
  margin: 0 auto;
}
.page-title { margin-top: 0; font-size: 22px; }
.page-hint { color: #909399; margin-bottom: 16px; }
.step-indicator { margin-bottom: 24px; }
.step-card { margin-bottom: 16px; }
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
.file-name {
  margin-left: 8px;
  color: #606266;
  font-size: 13px;
}
.form-hint { color: #909399; font-size: 12px; margin-left: 8px; }
.meta-info { color: #909399; font-size: 12px; }
.key-pair-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.key-separator {
  color: #909399;
  font-weight: bold;
}
</style>
```

> 上方模板给出了首段示例；Step 2/3/4 按 §1.3 大段 DOM 展开即可。

### 5.2 View 关键交互细节

#### onUpload 失败时的 preserve state
- 后端 413 / 422 等错误：仅 toast，`store.targetFile` / `store.baseFile` **保留**（用户无需重选；修改文件或重试即可）；
- 422 表头错误：toast detail 后保留文件，但 `store.canUpload` 仍 true（让用户重试相同文件不会因 UI 状态错误而 fail）。

#### onConfigure 失败回退
- 422（字段缺失）：toast detail，**保留当前 mappings / keys**，用户可即时修改重试；
- 409（job executed / expired）：toast detail，自动 `store.reset()` 回到 Step 1，并提示「任务已失效，请重新上传」。

#### onExecute 失败回退
- 409（未 configured）：toast 后回 Step 2；
- 409（expired）：toast 后自动 reset 到 Step 1；
- 5xx：toast 后保留 Step 3 state，可手动点重试。

#### onDownload 失败
- 401：toast「下载链接已失效，请重新执行」+ 自动切到 Step 3（execute 按钮）让用户重跑；
- 其它错误：toast。

#### onCleanUp 成功后回到 idle
- toast「已清理」；
- `store.reset()` 让 `stepIndex=0`，所有 card 切回 Step 1。

---

## 6. 错误约定（沿用全局 + 本模块新增）

| HTTP | 场景 | UI |
|------|------|----|
| 401 | download token 缺失 / 过期 | toast「下载链接已失效」+ 自动切 Step 3 |
| 409 | job expired / 已 executed / overwrite 缺 token（理论上走不到） | toast detail |
| 422 | 表头为空 / 重复 / mappings 字段缺失 / mode 非法 / keys 不等长 | toast detail |
| 5xx | pandas / openpyxl / DB 异常 | toast「服务异常，请稍后重试」 |
| 网络 | multipart 超时（> 60s） / 断网 | toast「网络异常，请稍后重试」 |

### 6.1 overwrite 二次确认（前端层）

```js
async function onConfigure() {
  // 前端校验
  if (!store.canConfigure) {
    ElMessage.warning('请完整填写主键和映射')
    return
  }
  // 含 overwrite 模式 → 二次确认
  let confirmToken = null
  if (store.hasOverwriteMapping) {
    try {
      await ElMessageBox.confirm(
        '本次配置含「覆盖原列」模式，将覆盖目标表的同名列。如已确认请继续；如需调整请返回修改。',
        '覆盖确认',
        { type: 'warning', confirmButtonText: '已确认，继续', cancelButtonText: '返回修改' }
      )
    } catch {
      return  // 用户选「返回修改」→ 不发请求
    }
    confirmToken = crypto.randomUUID()
  }
  // 调 store.patchConfig(confirmToken)
  await store.patchConfig(confirmToken)
}
```

---

## 7. 状态文案

| 场景 | 文案 |
|------|------|
| 上传成功 | 「解析成功：目标表 N 行 · 基础表 M 行」|
| 配置成功（无 warnings） | step 切到 3，digest 显示在 descriptions |
| 配置成功（有 warnings） | digest + 每条 warning 一行 `el-alert` |
| 执行成功 | step 切到 4，preview 渲染 |
| 下载成功 | 「已开始下载」|
| 清理成功 | 「已清理」|
| 下载链接失效（401）| 「下载链接已失效，请重新执行」|
| overwrite 二次确认 | 「本次配置含「覆盖原列」模式…」|
| 重置二次确认 | 「重置会清空当前任务…」|
| 清理二次确认 | 「删除该任务将一并清理…」|

---

## 8. 不实现的组件（明确范围）

- ❌ 不实现「文件上传进度条」（multipart 阻塞；后端 < 60s 通常 < 5s）
- ❌ 不实现「任务列表 / 历史」（24h 自动过期；前端无需查 list 端点）
- ❌ 不实现「拖拽多文件」（el-upload 的 limit=1；按 spec 只支持 1 对 target + 1 个 base）
- ❌ 不实现「上传到 OSS / 远程存储」（仅服务端本地解析）
- ❌ 不实现「多 base 表关联」（仅 1 target + 1 base）
- ❌ 不实现「公式注入提示」（后端 spec 边界：openpyxl 默认写为字符串）
- ❌ 不实现「VLOOKUP 风格的列号匹配」（仅字段名匹配，与 spec 一致）
- ❌ 不实现「下载历史 / 最近列表」
- ❌ 不实现「刷新后恢复上次未完成任务」（store state 全程在前端内存；刷新即丢失）
- ❌ 不实现「任务进度轮询」（execute 同步；无进度概念）
- ❌ 不实现「合并预览里高亮哪些 base 行被合并」（仅统计 `multi_match_count`；前端不强求明细）
- ❌ 不实现「mappings 的拖拽排序」（简单表格 + 上下移动按钮足够；v0.6.0 不必做）
- ❌ 不实现「后端 schema 描述实时 schema 校验」（仅前端 canConfigure 校验）

---

## 9. Test Plan

### 9.1 `api/cross_table_fill.js`（7 个函数）

| 用例 | 期望 |
|------|------|
| `uploadCrossTable({target, base, expires_in_hours:24})` | `POST /cross-table-fill/jobs`；FormData 含 target_file / base_file / expires_in_hours；`timeout >= 10000`（设 60000）|
| `uploadCrossTable({target, base})`（不传 expires_in_hours）| FormData 不含 expires_in_hours（后端默认 24h）|
| `getCrossTableJob(12)` | `GET /cross-table-fill/jobs/12` |
| `listCrossTableJobs({page:1, size:20})` | `GET /cross-table-fill/jobs?page=1&size=20` |
| `patchCrossTableConfig(12, payload)` | `PATCH /cross-table-fill/jobs/12/config`；body = payload |
| `executeCrossTable(12)` | `POST /cross-table-fill/jobs/12/execute`；无 body |
| `downloadCrossTableResult(12, 'tok')` | `GET /cross-table-fill/jobs/12/download?token=tok`；`responseType: 'blob'`；`timeout >= 10000`（设 60000）|
| `deleteCrossTableJob(12)` | `DELETE /cross-table-fill/jobs/12` |

### 9.2 `useCrossTableFillStore.js`（核心 getter + action）

| 用例 | 期望 |
|------|------|
| 初始 state | `stepIndex=0`、`step='idle'`、`targetFile=null`、`targetKeys=[]`、`mappings=[]` |
| `canUpload`: 两文件都 null | `false` |
| `canUpload`: 选齐两文件 | `true` |
| `canConfigure`: `targetKeys=[]` | `false` |
| `canConfigure`: 完整主键对 + 完整 mapping | `true` |
| `canConfigure`: 主键长度与 base_keys 不等 | `false`（防止 PATCH 时 422）|
| `hasOverwriteMapping`: 任意一条 mode='overwrite' | `true` |
| `addKeyPair()` 后 | `targetKeys.length` 与 `baseKeys.length` 同步 +1 |
| `addMapping()` 后 | `mappings.length` +1，默认 `mode='new_column'` |
| `cleanUp()` 后 | state 全部重置；`stepIndex=0` |

### 9.3 `views/CrossTableFill.vue`（4 步流程）

#### 9.3.1 Step 1：上传
- 初始：上传卡可见，「开始解析」按钮 disabled
- 选 target 后：文件名 chip 显示
- 选 base 后：第二个文件名 chip 显示；按钮 enable
- 点「开始解析」：`store.upload()` 被调用；按钮 loading；成功后 step 切到 `uploaded`，stepIndex=1
- 后端 413 响应：toast「文件超过 20 MB」；步骤保留
- 后端 422 响应（如重复 headers）：toast detail；步骤保留

#### 9.3.2 Step 2：配置
- 初始：所有 `targetKeys` / `baseKeys` / `mappings` 空
- 点「新增一对」：key-pair-row +1
- 点「移除」：key-pair-row -1（最后一行不可移除）
- 点「新增映射」：mappings +1（默认 new_column）
- 选 mode='overwrite'：触发 `ElMessageBox.confirm`；用户选取消 → row.mode 回退 new_column；用户选确定 → row.mode 写 overwrite
- 含 overwrite + 点「下一步」：触发 `ElMessageBox.confirm`「覆盖确认」；用户选取消 → 不发请求；用户选确定 → crypto.randomUUID() 生成 token + PATCH
- PATCH 成功：step 切到 `configured`，stepIndex=2
- PATCH 422（字段缺失）：toast detail；步骤保留
- 「上一步」：step 回 `uploaded`；state 不丢

#### 9.3.3 Step 3：试运行
- 初始：digest 显示；warnings 列表渲染
- 点「执行填充」：`store.execute()` 被调；按钮 loading
- 执行成功：step 切到 `executed`，stepIndex=3
- 执行 409（expired）：toast；自动 reset 到 Step 1
- 「上一步」：step 回 `uploaded`

#### 9.3.4 Step 4：结果
- 初始：5 项 summary 展示；preview 表渲染
- 「下载完整结果 xlsx」：调 `store.download()` + `downloadBlob(blob, 'cross_table_fill_<id>_filled_<ts>.xlsx')`；toast「已开始下载」
- 下载 401：toast「下载链接已失效」+ 自动切 Step 3
- 下载 5xx：toast「服务异常」
- 「清理任务」：触发 `ElMessageBox.confirm`；确认后 `store.cleanUp()` → step=idle
- 「上一步」：step 回 `configured`；可「修改配置后重新执行」

#### 9.3.5 跨步骤联动
- refresh 页面：state 不持久 → 自动重置 step=idle（符合 §8 不实现组件）

---

## 10. Assumptions

1. **后端 v0.6.0 已上线**；所有 7 个端点可用；OpenAPI 文件 `backend/openapi/cross_table_fill.json` 与本 spec 一致。
2. **`el-upload` 单文件**：本模块两张表各 1 个文件，不支持拖拽多文件；与 spec §8「不实现组件」一致。
3. **`crypto.randomUUID()` 浏览器原生**：要求浏览器 ≥ Chrome 92 / Firefox 95 / Safari 15.4；旧浏览器可用 `Math.random` 兜底（但 v0.6.0 不实现降级路径）。
4. **状态不持久化**：刷新页面 state 丢失；用户需重新上传。符合 spec §8「不实现持久化」。
5. **`downloadBlob` 工具复用 v0.5.8**：不新增 `utils/downloadBlob.js`；该函数已在周需求管理模块使用，前端沿用。
6. **el-table `:max-height=400`**：固定滚动区适合 1000 行预览；性能上 Element Plus 1000 行 × 10 列完全无压力。
7. **dropZone 与拖拽**：v0.6.0 不做拖拽；若用户希望，单独开 PR。
8. **侧边栏顺序**：第 6 项插在「HTML 转 Excel」之前，符合 README [§5.2](./README.md) 设计（数据加工与数据对齐相邻）。
9. **图标 `Connection`**：Material 图标语义为「节点互联」，符合「两表互联」语义；与「DSP 上传」的 `Upload`、`邮箱配置` 的 `Message` 形成对比。
10. **测试框架沿用 vitest + @vue/test-utils**：本模块测试与周需求管理 / PivotQuery 一致；不需要引入新依赖。

---

## 11. 修订记录

### v0.6.0（首次发布）

- 新增顶层模块「跨表数据填充」；
- 侧边栏第 6 项新增「跨表数据填充」icon `Connection`，to `/cross-table-fill`；
- 单页 4 步向导式 UI（el-steps + 多 el-card）；
- 新增 `views/CrossTableFill.vue`；
- 新增 `stores/useCrossTableFillStore.js`（含 4 步 state 与所有 getters / actions）；
- 新增 `api/cross_table_fill.js`（7 个函数对应 7 端点）；
- `overwrite` 强制前端 `ElMessageBox.confirm` 二次确认 + `crypto.randomUUID()` 生成 `confirm_token`；
- Step 4 渲染 `merge_multi_count` 的橙色 tag；
- 测试计划 9.3 覆盖 18 个 UI 交互用例。
