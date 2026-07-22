# SPEC：HTML-to-Excel 模块（标题定位 + 控件抽取 + Excel 导出）

> 版本：v0.2.0（2026-07-21）  
> 适用范围：`D:\Workspace\SparkMemo\backend\app\services\html_to_excel\`  
> 关联 SPEC：`backend/app/services/excel_export.py` 既有实现（复用 `_sanitize_formula`/`_auto_width` 风格）  
> 状态：v0.1.0 已实现并 22 单测通过；v0.2.0 增量（inspect + extract-by-index）正在实现

---

## 1. 背景 & 目标

### 1.1 背景
SparkMemo 当前已有 `excel_export.py` 用于把 DB 查询结果导出 xlsx（`/api/dsp-uploads/.../rows/export`、`/api/pivot-query/export`），但缺少"任意 HTML → 任意控件 → Excel"的通用能力。

用户场景：销售/运营人员在 NetSuite 等第三方系统页面 → 把页面 HTML 源码保存为 `.html` 文件（或内容是 HTML 的 `.txt` 等任意文本文件，本服务按"HTML 内容"识别，与扩展名解耦），然后指定一个控件标题（中/英），把该控件包含的所有内容导出为 xlsx，方便做线下账目核对。

### 1.2 目标
提供一个可被前端或 CLI 直接调用的服务，能力：

1. **输入**：HTML 文件路径 + 用户提供的控件标题（中文/英文，完整准确）。
2. **定位**：在 HTML 中找到该标题所在的"数据控件"，按规则推断其类型与范围。
3. **抽取**：把控件内容（含所有子行/子单元格）抽成结构化 JSON。
4. **导出**：把 JSON 转成 xlsx，保存到指定目录或返回二进制流供下载。
5. **降噪**：自动剔除脚本、装饰按钮、SVG、隐藏节点、巨型 JSON 配置块。

### 1.3 非目标
- 不渲染或执行页面 JavaScript（只解析静态 HTML）。
- 不处理动态加载占位（HTML 上"Loading..."占位 → 当作空表导出；需用户重新保存 HTML 才能拿到真实数据）。
- 不做 OCR / 截图识别（图片内容按用户要求直接跳过）。
- 不做模糊搜索、同义词匹配、近似匹配（用户要求"准确相等"）。

---

## 2. 输入与输出

### 2.1 输入
| 字段 | 类型 | 说明 |
|---|---|---|
| `html_path` | `str \| Path` | 已落盘的 HTML 内容文件路径（扩展名无要求：`.html` / `.htm` / 含 HTML 内容的 `.txt` 均可，本服务只把它当 HTML 文本解析） |
| `title` | `str` | 用户输入的控件标题（如 `Items`、`项目`、`销售团队`） |
| `output_dir` | `str \| Path` | xlsx 输出目录（默认 `backend/outputs/html_to_excel/`） |
| `filename_hint` | `str \| None` | 可选下载文件名提示；缺省按 `title + 时间戳` |

### 2.2 输出（成功）
```json
{
  "ok": true,
  "control_type": "table",
  "matched_title": "Items",
  "xlsx_path": "D:\\Workspace\\SparkMemo\\backend\\outputs\\html_to_excel\\Items_20260721_153045.xlsx",
  "download_filename": "Items_20260721_153045.xlsx",
  "rows": 23,
  "columns": 108,
  "warnings": []
}
```

### 2.3 输出（失败）
```json
{
  "ok": false,
  "error": "title_not_found",
  "message": "未找到标题为 'Itemz' 的控件",
  "candidates": ["Item", "Items Header", "Items Subtotal"]
}
```

错误码：
- `title_not_found` —— 无任何匹配
- `multiple_matches` —— 多个候选（按当前策略：直接返回候选列表，让调用方二选一，不选默认第一个）
- `html_unparseable` —— HTML 完全无法解析
- `empty_html` —— 解析后无业务节点（可能整页都被剔除）

### 2.4 输入：`/inspect` 端点

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `html_file` | `UploadFile` (multipart) | ✅ | 同一约定（≤20 MB） |

`/inspect` **不需要** title；目的是列出 HTML 中所有可下载的控件。

### 2.5 输出：`/inspect` 成功响应

```json
{
  "ok": true,
  "html_size_kb": 3131,
  "controls": [
    {
      "index": 0,
      "control_type": "table",
      "suggested_title": "Item",
      "title_source": "thead-th",
      "row_count": 23,
      "column_count": 107,
      "preview": {
        "headers": ["Line Number", "Item Status", "Original Promise Delivery", "Promised Delivery (ETA)", "Promised Shipment Date"],
        "first_rows": [
          ["1", "OK", "", "", ""],
          ["2", "Alert", "", "", ""],
          ["3", "OK", "", "", ""]
        ]
      }
    }
  ]
}
```

字段约定：
- `index`：0-based stable 下标（同一个响应内全程一致）。
- `suggested_title`：best-effort，按 §4.6 优先级启发式提取。
- `row_count`：去掉 tfoot 后实际数据行数。
- `column_count`：列数。
- `preview.headers` / `preview.first_rows`：限 **前 3 行 × 前 5 列**（R9 防敏感泄露）。

### 2.6 错误响应：`/inspect`

| 场景 | HTTP | `error` |
|---|---|---|
| 文件 > 20 MB | 413 | （detail 字符串） |
| HTML 不可解析 | 422 | `html_unparseable` |
| 解析后无业务节点 | 422 | `empty_html` |
| 解析成功但无显著控件 | 200 | `controls: []`（不算错，前端提示"未发现表格"） |

### 2.7 输入：`/extract-by-index` 端点

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `html_file` | `UploadFile` (multipart) | ✅ | 同 §2.4 |
| `index` | `int` (form) | ✅ | 上一次 `/inspect` 响应中 `controls[i].index` 的 `i` |
| `filename_hint` | `string` (form) | ❌ | 同 §2.1 |

### 2.8 输出：`/extract-by-index` 成功响应

与 §2.2 完全一致 schema（含 `xlsx_path`、`download_filename`、`rows`、`columns`、`warnings`）。

### 2.9 错误响应：`/extract-by-index`

| 场景 | HTTP | `error` |
|---|---|---|
| 文件 > 20 MB | 413 | （detail 字符串） |
| index < 0 或 ≥ len(controls) | 422 | `index_out_of_range`（响应 `detail.candidates` 列出所有 `suggested_title`，方便用户重新选择） |
| HTML 不可解析 | 422 | `html_unparseable` |

---

## 3. 整体架构

```
backend/app/services/html_to_excel/
├── __init__.py
├── pipeline.py            # 总编排 (HtmlToExcelPipeline.run / inspect / run_by_index)
├── parser.py              # HTML 解析 + 降噪 (HTMLParser)
├── locator.py             # 标题定位 (TitleLocator)        [v0.1.0]
├── inspector.py           # 枚举所有候选控件（v0.2.0 新增）
├── recognizers/
│   ├── __init__.py
│   ├── base.py            # Recognizer 抽象基类
│   ├── table.py           # <table> 控件识别
│   ├── div_grid.py        # div-based 重复行表格
│   ├── field_group.py     # label/value 字段组
│   └── list_block.py      # <ul>/<dl> / 列表式
├── cleaner.py             # 文本/HTML 实体清洗
├── schemas.py             # JSON 中间表示 + InspectionResult dataclass（v0.2.0 新增）
└── writer.py              # JSON → xlsx (ExcelWriter)
```

依赖：本服务复用既有的 `excel_export.py` 模块的工具函数（`_sanitize_formula`、`_auto_width`、`_export_timestamp`），不重复实现。

---

## 4. 流水线阶段

### 4.1 阶段 ① HTML 解析与降噪（`parser.py`）

| 步骤 | 规则 |
|---|---|
| 1.1 选解析器 | `lxml` 优先；失败回退 `html.parser` |
| 1.2 移除脚本/样式 | 递归 `extract()` 掉 `<script>`、`<style>`、`<noscript>` |
| 1.3 移除隐藏装饰 | `style="display:none"` 的元素 + `class` 含 `noprint` / `uir-button` 的容器 |
| 1.4 移除巨型 JSON | `<script type="application/json">` 与 `<script>` 里 `var data = {…}` / `var _dynamicRecordSpecificData` / `var _defaultLocale` 等（用正则检测 `{` ≥ 500 字符的 JSON 字面量并 strip） |
| 1.5 移除 SVG/IMG | 用户要求跳过图片；`<svg>`、`<img>` 整段 `extract()` 掉（仅保留可读文本） |
| 1.6 移除页眉/遮罩 | `#div__header`、`#timeoutblocker`、`#timeoutpopup` 与 `class="ns-child-component noprint"` 等 |

接口：
```python
class HTMLParser:
    def parse(self, html_path: Path) -> BeautifulSoup:
        """返回降噪后的 soup 树根节点"""
```

### 4.2 阶段 ② 标题定位（`locator.py`）

#### 4.2.1 文本归一化
```python
def _normalize(text: str) -> str:
    return (
        text
        .replace("\u00a0", " ")   # &nbsp; → 空格
        .replace("\u2003", " ")
        .replace("\u2002", " ")
        .replace("\n", " ")
        .replace("\t", " ")
        .strip()
    )
def _collapse_spaces(s: str) -> str:
    return " ".join(s.split())
```
比对规则：两侧文本都先 `normalize + collapse`，再**不区分大小写**做完全相等（按 SPEC §5.1 决策）。

#### 4.2.2 候选节点收集（按优先级）
`TitleLocator.find(title) -> list[MatchCandidate]` 遍历顺序：

| 优先级 | 来源 | 匹配条件 |
|---|---|---|
| 1 | `<th>` 文本 | `_collapse_spaces(th.get_text()) == _collapse_spaces(title)` |
| 2 | `<thead>` 里 `<div class="listheader">` 等头部文本 | 同上 |
| 3 | `<dt>` / `<caption>` / `<legend>` | 同上 |
| 4 | 任意节点的 `aria-label` / `title` / `alt` 属性 | 属性值与 title 完全相等 |
| 5 | 字段控件 label：`data-nsps-label` 属性 / 内层 `<a>` 文本（NetSuite `uir-label-span > a`） | 文本归一后相等 |
| 6 | `<h1>` – `<h6>` | 同上 |
| 7 | `<label>` `for` 指向的 input 之 label 文本 | 同上 |

**冲突策略：**
- 多个候选 → 返回全部，按 §4.2.3 处理。
- 完全相等 0 个 + 用户输入近似（仅大小写或空格不同） → 返回 `title_not_found` 并附 1 个候选。

#### 4.2.3 选中策略
按 SPEC §5.2：多个匹配时返回全部候选给前端二选一；调用方不传选择 → 默认取第一个（页面 DOM 顺序最早）。

#### 4.2.4 数据结构
```python
@dataclass
class MatchCandidate:
    node: bs4.element.Tag       # 命中节点
    source: str                 # "th" | "listheader" | "aria-label" | "nsps-label" | ...
    matched_text: str           # 原始命中文本
    parent_path: list[str]      # 祖先节点层级描述，用于调试
```

### 4.3 阶段 ③ 控件范围识别（`recognizers/`）

#### 4.3.1 接口
```python
class Recognizer(ABC):
    priority: int
    @abstractmethod
    def matches(self, node: bs4.element.Tag) -> bool: ...
    @abstractmethod
    def extract(self, node: bs4.element.Tag) -> ExtractedControl: ...
```

`ExtractedControl` 见 §6.1。

#### 4.3.2 识别器实现

| 识别器 | priority | `matches` 条件 | `extract` 范围 |
|---|---|---|---|
| `TableRecognizer` | 10 | 标题节点向上爬升过程中遇到最近的 `<table>` | 该 `<table>` 的 `<thead>` + `<tbody>`，全部 `<tr>` |
| `DivGridRecognizer` | 20 | 祖先是 `<div role="table">` 或 `<div role="rowgroup">`；或祖先 div 含 ≥ 2 个 class 一致的 `<div role="row">` 兄弟 | 同级所有 row + 列模板（首个 row 的子元素） |
| `FieldGroupRecognizer` | 30 | 标题是 `<legend>` / `<h2>`-`<h4>` / `<div data-nsps-label="…">` 含 `data-field-group-row` 的 tr | 该组容器内所有 label/value 子节点 |
| `ListBlockRecognizer` | 40 | 祖先是 `<ul>` / `<ol>` / `<dl>` | 该 list 所有项，每项一个"键/值"两列 |

**爬升算法：**
```python
def find_control_root(node):
    for ancestor in node.iter_ancestors():
        for rec in RECOGNIZERS_BY_PRIORITY:
            if rec.matches(ancestor):
                return rec, ancestor
    # 兜底：返回整个 <body>
    return FieldGroupRecognizer(), node.find_parent("body")
```

#### 4.3.3 特殊处理
- **嵌套表**：外层 `<table>` 内有 `<table>` → 只导外层，内层以单元格字符串 `(subtable)` 占位；不递归拆 sheet（按 SPEC §5.3 用户决策）。
- **Loading 占位**：tbody 内只有 `<tr class="uir-loading-row">` 或 `<tr class="uir-nodata-row">` → 视为空表，照常出 sheet，但首行写 `(空 — Loading placeholder)`。
- **`<table>` 内多个 `<thead>` / `<tfoot>`**：合并为一组列定义；footer 行也作为普通行导出（在尾部）。

### 4.4 阶段 ④ 内容抽取 → JSON 中间表示

#### 4.4.1 字段值清洗（`cleaner.py`）

| 输入模式 | 输出 |
|---|---|
| `&nbsp;`、`<img alt="Checked">` 仅存在 → `true` | bool |
| `&nbsp;`、`<img alt="Unchecked">` 仅存在 → `false` | bool |
| `<a class="dottedlink" href="X">Text</a>` | `{ text, href }` |
| `<div style="background-color:green;">&nbsp;</div>` | `"OK"` (颜色归一化: green→OK, red→Alert, 其它保留原文) |
| `<span class="uir-field-truncated-value" data-ns-tooltip="完整原文">(more...)</span>` | tooltip 全文 |
| `<br>` 多个 | 合并为 `\n` |
| `&amp;` 等 HTML 实体 | 反转 |
| 数字字符串 `751,653.00` | 原样保留（字符串），由 writer 决定是否转 number |
| 日期字符串 `8/21/2025` / `8/21/2025 5:35 am` | 原样保留 + 标记 `type=date/datetime` |

#### 4.4.2 通用单元格字典（写入 `cells[]`）
```python
{
  "value": "...",        # 字符串或 bool
  "type": "text|link|number|date|datetime|boolean|status|tooltip|html",
  "href": "...",         # 仅 link 类型
  "tooltip": "...",      # 仅 tooltip 类型
  "raw_html": "..."      # 仅 html 类型且 opt-in 时（默认关闭）
}
```

#### 4.4.3 列定义推断
对 `TableRecognizer`：表头若存在 → 用表头单元格文本做列名；缺表头 → 用 `column_N` 自增名。
对 `DivGridRecognizer`：列名从 `role="columnheader"` 或首行子元素的 `data-label` / `data-nsps-label` 取。
对 `FieldGroupRecognizer`：固定两列 `(Label, Value)`。
对 `ListBlockRecognizer`：固定两列 `(Index, Text)` 或 `(Key, Value)`。

### 4.5 阶段 ⑤ JSON → xlsx（`writer.py`）

#### 4.5.1 Workbook 布局
- 默认一个控件一张 sheet：`Sheet1 = "Items"`。
- 列名截断到 31 字符（Excel 限制）；超长去重 `~1`、`~2`。

#### 4.5.2 列类型映射

| JSON `type` | Excel 单元格 | number_format |
|---|---|---|
| `text` / `status` / `tooltip` | 字符串 | `@` |
| `number` | 数值（去掉千分位逗号） | `#,##0.00` |
| `integer` | 整数 | `0` |
| `date` | `datetime` | `m/d/yyyy` |
| `datetime` | `datetime` | `m/d/yyyy h:mm am/pm` |
| `boolean` | `TRUE` / `FALSE` | n/a |
| `link` | 字符串 `text (href)` | `@`（不写超链，避免外网提示） |
| `html` | 空（默认跳过）或纯文本 stripped | `@` |

#### 4.5.3 通用规范
- 全部 `_sanitize_formula`（复用 `excel_export.py`）。
- 全部 `_auto_width`（复用）。
- 冻结首行 `ws.freeze_panes = "A2"`。
- 表头加粗 + 底色浅灰（与现有 `excel_export.py` 风格一致）。

#### 4.5.4 文件名
`{filename_hint or matched_title}_{_export_timestamp()}.xlsx`，扩展名补齐。

#### 4.5.5 输出路径
- 默认 `backend/outputs/html_to_excel/{filename}.xlsx`。
- 目录不存在自动创建。

---

### 4.6 阶段 ⑥ 枚举所有控件（v0.2.0 新增）

> 触发：`/inspect` 与 `/extract-by-index` 都先走这一步。

| 步骤 | 规则 |
|---|---|
| 6.1 输入 | 已降噪后的 `BeautifulSoup`（同 §4.1 输出） |
| 6.2 收集候选 | 遍历 `<table>` / `[role="table"]` / `[role="rowgroup"]` / `<legend>` + 上方 `<h2>` `<h3>` / `<ul>` `<ol>` `<dl>` / `data-nsps-type="field"` 的祖先容器 |
| 6.3 recognizer.matches 过滤 | 调 `find_control_root(node)`；若 `rec` 为 `None` 跳过 |
| 6.4 显著过滤 | 见规则表（下方 §4.6.1） |
| 6.5 摘要生成 | 复用 §4.4 recognizer.extract → 抽取 `(headers, 前 3 行 × 前 5 列)` 当 preview，启发式提 `suggested_title` |
| 6.6 缓存节点引用 | `DetectedControl.node` 保留 `bs4.element.Tag`，供 `run_by_index` 复用 |

#### 4.6.1 「显著表格」过滤规则

| 规则 | 跳过原因 |
|---|---|
| `class` 含 `loading-row` / `nodata-row` | Loading 占位 |
| 唯一一行 `<tr>` 且该 tr 全是 `<th>` | 纯表头，无数据 |
| `row_count == 0`（去除 tfoot 后） | 真的空表 |
| `column_count == 0` 且 `control_type != "field_group"` | 字段组可保留 |
| 嵌套表中内层 `<table>`（祖先是 `<table>`） | 保留外层 |
| `<form>` 内纯按钮容器（heuristic：`form.find_all('table') == []` 且无 label/value 字段内容） | 非数据控件 |

#### 4.6.2 `suggested_title` 启发式优先级

| 顺位 | 源 | `title_source` 标识 |
|---|---|---|
| 1 | 节点最近 `<th>` 文字 | `thead-th` |
| 2 | 节点 `aria-label` 属性 | `aria-label` |
| 3 | 节点上方最近的 `<h2>` `<h3>` `<h1>` | `prev-h2` / `prev-h3` / ... |
| 4 | `<legend>` 子文本 | `legend` |
| 5 | 节点 `id` 属性 | `id` |
| 6 | 兜底空字符串 | `fallback` |

#### 4.6.3 内部接口（`inspector.py`）

```python
@dataclass
class ControlPreview:
    headers: list[str] = field(default_factory=list)
    first_rows: list[list[str]] = field(default_factory=list)

@dataclass
class ControlSummary:
    index: int = 0
    control_type: str = ""
    suggested_title: str = ""
    title_source: str = ""
    row_count: int = 0
    column_count: int = 0
    preview: ControlPreview = field(default_factory=ControlPreview)
    def to_dict(self) -> dict: ...

@dataclass
class DetectedControl:
    summary: ControlSummary       # 序列化给前端
    node: bs4.element.Tag         # 内部传给 run_by_index
    control: ExtractedControl     # 完整 ExtractedControl（已 extract；run_by_index 直接复用）

class HTMLInspector:
    def inspect(self, soup: BeautifulSoup) -> list[DetectedControl]: ...
```

> 设计选择：`DetectedControl.control` 在 inspect 阶段就做完整 extract，避免 `run_by_index` 再跑一遍 recognizer（节省 2s+）。

#### 4.6.4 流水线对外接口（`pipeline.py` 扩展）

```python
class HtmlToExcelPipeline:
    def inspect(self, html_path: Path | str) -> InspectionResult: ...
    """返回 InspectionResult，ok=True 时 controls: list[ControlSummary]"""
    
    def run_by_index(self, html_path, index, output_dir,
                     filename_hint: str | None = None) -> ExtractionResult: ...
    """与 .run() 同 schema 输出；走 inspect 找到 controls[index]，复用其 node 与 ExtractedControl"""
```

---

## 5. 设计决策表（用户已确认）

| 编号 | 决策点 | 选择 | 备注 |
|---|---|---|---|
| 5.1 | 标题比对大小写 | 不敏感 | 中英文都生效，规整化 + collapse 空格 |
| 5.2 | 多匹配处理 | 返回全部候选，由调用方二选一；不传则默认 DOM 序首匹配 | 避免歧义误伤 |
| 5.3 | 嵌套控件处理 | 只导外层，内层以字符串占位 | 实现简单，UX 清晰 |
| 5.4 | 控件类型识别 | 智能识别（4 种 recognizer） | 用户确认"智能划分" |
| 5.5 | 标题匹配源 | 全部可能位置（th / thead div / dt / legend / aria-label / nsps-label / h1-h6） | 用户确认"所有可能位置" |
| 5.6 | 空表处理 | 创建空 sheet，表头 + 首行 `(空)` | 不报错 |
| 5.7 | 输出形式 | 保存为文件，返回 `xlsx_path` + `download_filename` | 可被前端 `<a href>` 触发下载 |
| 5.8 | 列表预览数据规模（v0.2.0） | 前 3 行 × 前 5 列 | 防敏感数据泄露 |
| 5.9 | `inspect` 与 `extract-by-index` 的关系（v0.2.0） | 每次 `/extract-by-index` 都重新 `/inspect`，**不**持久化 session | 实现简单，无状态 |

---

## 6. 数据契约

### 6.1 `ExtractedControl`（Python 内部）
```python
@dataclass
class ExtractedCell:
    value: object
    type: str  # text|link|number|date|datetime|boolean|status|tooltip
    href: str | None = None
    tooltip: str | None = None

@dataclass
class ExtractedRow:
    cells: list[ExtractedCell]
    is_subtotal: bool = False  # <tfoot> 行或 class 含 totals

@dataclass
class ColumnDef:
    key: str
    type: str  # 推断类型
    source: str  # "th"|"data-label"|"legend"|...
    index: int

@dataclass
class ExtractedControl:
    title: str
    matched_text: str
    source: str
    control_type: str  # "table" | "div_grid" | "field_group" | "list_block"
    columns: list[ColumnDef]
    rows: list[ExtractedRow]
    warnings: list[str]
```

### 6.1.x `InspectionResult`（v0.2.0 新增）

```python
@dataclass
class ControlPreview:
    headers: list[str] = field(default_factory=list)
    first_rows: list[list[str]] = field(default_factory=list)

@dataclass
class ControlSummary:
    index: int = 0
    control_type: str = ""
    suggested_title: str = ""
    title_source: str = ""
    row_count: int = 0
    column_count: int = 0
    preview: ControlPreview = field(default_factory=ControlPreview)

@dataclass
class InspectionResult:
    ok: bool = False
    error: str | None = None           # html_unparseable | empty_html
    message: str | None = None
    html_size: int = 0                 # bytes
    controls: list[ControlSummary] = field(default_factory=list)
```

`InspectionResult.to_dict()` schema：
```json
{
  "ok": true,
  "html_size_kb": 3131,
  "controls": [{"index": 0, "control_type": "table", ...}]
}
```

### 6.2 JSON 输出（给 ExcelWriter）
```json
{
  "control": {
    "title": "Items",
    "control_type": "table",
    "columns": [
      {"key": "Line Number", "type": "number", "source": "th", "index": 0},
      {"key": "Item", "type": "link", "source": "th", "index": 9},
      {"key": "Description", "type": "text", "source": "th", "index": 12}
    ],
    "rows": [
      {
        "cells": [
          {"value": "1", "type": "number"},
          {"value": "HLL060240327582B", "type": "link", "href": "/app/common/item/item.nl?id=172633"},
          {"value": "Legrand - 45U Network rack without side panels", "type": "text"}
        ]
      }
    ],
    "warnings": []
  }
}
```

### 6.3 API 响应
见 §2.2 / §2.3。

---

## 7. 与现有 `excel_export.py` 的复用

| 复用项 | 来源 |
|---|---|
| `_sanitize_formula(value)` | 直接 import |
| `_auto_width(headers, rows)` | 直接 import |
| `_export_timestamp()` | 直接 import |
| 模块 docstring 风格 / 中文 docstring / `from __future__ import annotations` | 沿用 |

不重复实现。

---

## 8. API 端点草案（FastAPI）

挂在现有 `backend/app/api/` 下，新增 `html_to_excel.py`：

```python
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from ..services.html_to_excel import HtmlToExcelPipeline

router = APIRouter(prefix="/api/html-to-excel", tags=["html-to-excel"])

@router.post("/extract")
async def extract(
    html_file: UploadFile = File(..., description="HTML 文件"),
    title: str = Form(..., description="控件标题（中文/英文）"),
    filename_hint: str | None = Form(None),
) -> dict:
    """
    上传 HTML + 标题 → 服务端定位 → 生成 xlsx → 返回下载信息
    """
    ...

@router.get("/download/{filename}")
async def download(filename: str):
    """
    下载已生成的 xlsx（鉴权待与现有 session/cookie 策略对齐）
    """
    return FileResponse(
        path=OUTPUT_DIR / filename,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
```

错误 → `HTTPException` 映射：
- `title_not_found` → 404
- `multiple_matches` → 409（响应体含 `candidates`）
- `html_unparseable` / `empty_html` → 422

### 8.x v0.2.0 追加路由

```python
@router.post("/inspect")
async def inspect(
    html_file: UploadFile = File(..., description="HTML 文件")
) -> dict:
    """
    列出 HTML 中所有可下载的控件（带 index + preview + 行/列数）。
    
    200: 返回 { ok, html_size_kb, controls: [ControlSummary] }
    413/422: 文件超限 / 解析失败（响应体含 InspectionResult 全部字段）
    """

@router.post("/extract-by-index")
async def extract_by_index(
    html_file: UploadFile = File(...),
    index: int = Form(..., description="0-based，对应 /inspect 响应的 controls[i].index"),
    filename_hint: str | None = Form(None),
) -> dict:
    """
    按 index 抽控件 → 生成 xlsx → 返回下载信息。
    
    200: 与 /extract 同 schema（含 xlsx_path / download_filename）
    413: 文件超限
    422 (index_out_of_range): 响应 detail.candidates 列出所有 suggested_title
    422 (html_unparseable): 解析失败
    """
```

错误 → `HTTPException` 映射（v0.2.0 新增）：
- `index_out_of_range` → 422
- `inspect`: 文件可解析但 `controls=[]` → 仍 200（不算错）

---

## 9. 边界处理 / 失败模式

| 场景 | 行为 |
|---|---|
| 用户标题在 HTML 完全不存在 | 返回 `title_not_found`，附 normalized 后的相近候选（仅大小写/空格） |
| 标题存在但定位到的控件是空（Loading） | 创建 sheet，写表头 + 第 1 行 `(空 — Loading placeholder or empty table)` |
| 标题命中多个 | 返回 `multiple_matches` + candidates |
| `<table>` 内有 `<table>` | 只导外层；内层单元字符串占位 `(subtable, N rows)` |
| 链接 / 内嵌字段 / 富文本 | 按 §4.4.1 清洗规则归一 |
| Hidden input 字段 | **不**进 JSON（用户目标是"标题所在的控件的内容"）；隐藏的 system 字段另行单独 sheet 可作扩展 |
| HTML 残破导致 BS 解析崩溃 | 捕获异常返回 `html_unparseable` |
| 输出目录不存在 | 自动 `mkdir(parents=True, exist_ok=True)` |
| 文件名冲突 | 自动追加时间戳 |
| 标题超长导致 sheet 名 > 31 字符 | 截断 + `~N` 去重 |
| 中英混合 case（如 `Item` vs `item`） | 大小写不敏感命中首匹配 |
| (v0.2.0) `inspect` 返回 `controls: []`（HTML 内确实无显著控件） | 仍 200，让前端提示"未发现表格" |
| (v0.2.0) `/extract-by-index` index 越界 | 422 `index_out_of_range`，响应 `detail.candidates` 列出全部 suggested_title |

---

## 10. 单元测试计划

文件位置：`backend/tests/test_html_to_excel.py`（新增）

| Test | 覆盖场景 |
|---|---|
| `test_locator_exact_match_caseinsensitive` | 标题大小写无关 |
| `test_locator_th_priority` | `<th>` 优先于 `<h1>` |
| `test_locator_no_match` | 返回 not_found |
| `test_locator_multiple_returns_all` | 多匹配 |
| `test_table_recognizer_simple` | 简单 table |
| `test_table_recognizer_with_tfoot` | 含合计行的 table |
| `test_table_recognizer_loading_placeholder` | `uir-loading-row` → 空 sheet |
| `test_div_grid_recognizer` | div-based grid |
| `test_field_group_recognizer` | label/value 字段组 |
| `test_list_block_recognizer` | ul/ol 列表 |
| `test_cleaner_amp_entity` | `&amp;` 反转 |
| `test_cleaner_nbsp_to_empty` | `&nbsp;` → "" |
| `test_cleaner_truncated_recover_tooltip` | `(more...)` → tooltip |
| `test_cleaner_checkbox` | Checked / Unchecked |
| `test_writer_formula_sanitize` | `=SUM()` 加前缀 |
| `test_writer_column_width` | 列宽自动 |
| `test_pipeline_end_to_end_with_table_html` | fixture HTML → xlsx 字节流对比 |
| `test_pipeline_end_to_end_with_div_grid` | 同上，div-grid |
| `test_pipeline_field_group` | field-group 模式 |
| `test_pipeline_no_match_error_json` | 失败响应 schema |

### v0.2.0 新增 6 条单测

| Test | 覆盖 |
|---|---|
| `test_inspect_returns_simple_table` | simple_table.html → 至少 1 个 control，`controls[0].row_count ≥ 2` |
| `test_inspect_filters_loading_placeholder` | loading_placeholder.html → `controls: []` |
| `test_inspect_skips_inner_nested_table` | nested_table fixture → 只返回外层 |
| `test_inspect_meta_correct_for_netsuite_subset` | netsuite_items_subset.html → controls[0].row_count=2, columns=4 |
| `test_extract_by_index_matches_extract_by_title` | run_by_index(0) 输出 rows/columns 与 run(title="Item") 一致 |
| `test_extract_by_index_out_of_range` | index=99 → ExtractionResult.error=`index_out_of_range` |

测试用 fixture 放 `backend/tests/fixtures/html_to_excel/`：
- `simple_table.html`：标准 thead/tbody。
- `netsuite_items_subset.html`：NetSuite 风格，有 `data-ns-tooltip` / `class="uir-machine-row"`。
- `div_grid.html`：Bootstrap/Ant Design 风格 div-based grid。
- `field_group.html`：NetSuite 字段组。
- `loading_placeholder.html`：表格只有 Loading 占位行。
- `nested_table.html`（v0.2.0 新增）：HTML 包含 `<table>` 内嵌 `<table>`，inspect 应只返回外层。

---

## 11. 依赖

新增 `requirements.txt`（追加）：
- `beautifulsoup4>=4.12`
- `lxml>=5.0`
- `openpyxl>=3.1` （已有）

不引入：pandas（避免重复内存；如有必要可再加）。

---

## 12. 落地步骤（按本 SPEC 实现）

1. 创建目录 `backend/app/services/html_to_excel/` 与子目录 `recognizers/`、`backend/tests/fixtures/html_to_excel/`。
2. 写 `schemas.py`（§6.1 dataclass）。
3. 写 `parser.py`（§4.1）。
4. 写 `cleaner.py`（§4.4.1）。
5. 写 `recognizers/base.py` 与四个具体实现（§4.3）。
6. 写 `locator.py`（§4.2）。
7. 写 `writer.py`（§4.5）。
8. 写 `pipeline.py` 串联。
9. 写 `__init__.py` 暴露 `HtmlToExcelPipeline.run()`。
10. 在 `backend/app/api/` 新增 `html_to_excel.py` 挂 FastAPI 路由（§8）。
11. 在 `backend/app/main.py` 注册 router。
12. 写 19 个单元测试（§10）。
13. 在 `backend/requirements.txt` 追加依赖（§11）。
14. 复制现有 `D:\Workspace\SparkMemo\table.txt`（内容即 HTML body）到 `backend/tests/fixtures/html_to_excel/netsuite_items.html`，跑端到端验证：以 `Items` 作标题生成 xlsx，肉眼对比 23 行 × 108 列。
15. 更新项目根 `README.md` 增加"HTML → Excel"章节（含调用示例）。
16. v0.2.0 增量：写 `inspector.py` 与 dataclass `ControlPreview` / `ControlSummary` / `InspectionResult`。
17. v0.2.0 增量：扩展 `schemas.py` 加 `InspectionResult` / `ControlSummary` / `ControlPreview`。
18. v0.2.0 增量：扩展 `pipeline.py` 加 `inspect()` / `run_by_index()`。
19. v0.2.0 增量：扩展 `__init__.py` 暴露 `HtmlToExcelPipeline.inspect` / `.run_by_index` 与 `InspectionResult`。
20. v0.2.0 增量：扩展 `backend/app/api/html_to_excel.py` 加 `/inspect` 与 `/extract-by-index` 两个端点。
21. v0.2.0 增量：加 `nested_table.html` fixture + 6 个单测（§10 v0.2.0 部分）。

---

## 13. 开放问题 / 风险登记

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 大文件（3 MB+）解析慢 | `lxml` + 流式 `iter()` 而不是 `get_text()`；实测目标 < 5s |
| R2 | NetSuite 单行 30K 字符表头导致 BS 卡死 | recognizer 用 `find_all` + 逐 td 解析 |
| R3 | 用户标题含特殊字符（如括号 / 斜杠） | 文件名清洗函数 |
| R4 | 链接列超 1000 字符 | `_auto_width` 上限 50，超长截断展示 + tooltip 完整内容 |
| R5 | 嵌套表内容丢失 | 当前规则：占位字符串；未来扩展点 §13.1 |
| R6 | 多 sheet 需求（一个控件导出多 sheet） | 当前不支持；如需，未来把 `ExtractedControl.rows` 拆 group |
| R7 | 鉴权与速率限制 | 走现有 session 中间件；上传大小限制单独配置 |
| R8 (v0.2.0) | `inspect` + `extract-by-index` 两次重复解析大文件 | 当前接受（2s/次 < 用户耐心）；未来 LRU 缓存 |
| R9 (v0.2.0) | `preview` 数据可能含敏感信息 | 限前 3 行 × 前 5 列；不输出整张表 |
| R10 (v0.2.0) | `inspect` 与 `extract-by-index` 之间索引可能错位（检测算法变化） | 每次 inspect 重新建立 0-based index；同一响应内一致 |

---

## 14. 调用示例（落地后）

### 14.1 CLI
```bash
conda activate dev_env
python -m backend.app.services.html_to_excel \
    --html D:/Workspace/SparkMemo/table.html \
    --title Items \
    --output-dir D:/Workspace/SparkMemo/backend/outputs/html_to_excel
```

### 14.2 HTTP
```bash
curl -X POST http://localhost:8000/api/html-to-excel/extract \
    -F "html_file=@D:/Workspace/SparkMemo/table.html" \
    -F "title=Items" \
    -F "filename_hint=SO3000273-items"
```
返回：
```json
{
  "ok": true,
  "control_type": "table",
  "matched_title": "Items",
  "xlsx_path": "D:\\Workspace\\SparkMemo\\backend\\outputs\\html_to_excel\\SO3000273-items_20260721_153045.xlsx",
  "download_filename": "SO3000273-items_20260721_153045.xlsx",
  "rows": 23,
  "columns": 108,
  "warnings": []
}
```
随后：
```bash
curl -OJ http://localhost:8000/api/html-to-excel/download/SO3000273-items_20260721_153045.xlsx
```

### 14.3 v0.2.0 HTTP：先 inspect，再按 index 下载（无需标题）

**Step 1：** 列出所有候选控件（≤ 20 MB，无 title 字段）
```bash
curl -X POST http://localhost:8000/api/html-to-excel/inspect \
    -F "html_file=@D:/Workspace/SparkMemo/table.html"
```
返回：
```json
{
  "ok": true,
  "html_size_kb": 3131,
  "controls": [
    {
      "index": 0,
      "control_type": "table",
      "suggested_title": "Item",
      "title_source": "thead-th",
      "row_count": 23,
      "column_count": 107,
      "preview": {
        "headers": ["Line Number", "Item Status", "..."],
        "first_rows": [["1", "OK", ""], ["2", "Alert", ""], ["3", "OK", ""]]
      }
    },
    {
      "index": 1,
      "control_type": "field_group",
      "suggested_title": "Primary Information",
      "title_source": "legend",
      "row_count": 4,
      "column_count": 2,
      "preview": {"headers": ["Label", "Value"], "first_rows": [["Document Number", "SO3000273"]]}
    }
  ]
}
```

**Step 2：** 用户选了卡片 `index=0`（最显著表）→ 直接下载
```bash
curl -X POST http://localhost:8000/api/html-to-excel/extract-by-index \
    -F "html_file=@D:/Workspace/SparkMemo/table.html" \
    -F "index=0" \
    -F "filename_hint=SO3000273-items"
```
返回（与 §2.2 同 schema）：
```json
{
  "ok": true,
  "control_type": "table",
  "matched_title": "Item",
  "xlsx_path": "D:\\Workspace\\SparkMemo\\backend\\outputs\\html_to_excel\\SO3000273-items_20260721_153045.xlsx",
  "download_filename": "SO3000273-items_20260721_153045.xlsx",
  "rows": 23,
  "columns": 107,
  "warnings": []
}
```

---

## 15. 变更记录

| 日期 | 版本 | 变更人 | 说明 |
|---|---|---|---|
| 2026-07-21 | v0.1.0 | opencode | 初稿，覆盖背景、流水线、合约、测试计划 |
| 2026-07-21 | v0.2.0 | opencode | 新增 `/inspect` 与 `/extract-by-index` 端点，无标题快速下载；新增 `inspector.py` 模块、`InspectionResult` 契约、`ControlSummary`/`DetectedControl` dataclass、`run_by_index()` 流水线方法；新增 6 个单测；新增 §4.6 枚举阶段 + §4.6.1 显著过滤 + §4.6.2 标题启发式；决策表 R8-R10 风险登记 |
