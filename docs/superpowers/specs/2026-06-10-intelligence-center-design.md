# Intelligence Center (情报站) 设计方案

> 状态：待实现  
> 版本：v1.0  
> 日期：2026-06-10

---

## 1. 定位与边界

**定位：** NebulaShare 的「信息中枢」——聚合多源信息，支持阅读、筛选、收藏、回顾。

**边界内：**
- 采集 → 存储 → 展示 → 筛选 → 收藏 → 搜索
- 三种来源：Hermes 播报、RSS 订阅、手动录入

**边界外（明确不做）：**
- 不替代 RSS 阅读器（如 Inoreader）的深度功能（如规则过滤、邮件转发）
- 不做内容推荐算法（无用户画像、无协同过滤、无热榜排序）
- 不做社交分享（生成分享链接、嵌入卡片等）

---

## 2. 数据架构

### 2.1 数据库选择：SQLite

理由：NebulaShare 运行在 Raspberry Pi 4B 上，资源有限。SQLite 零运维、文件级存储、Python 原生支持，足够支撑情报站的数据量和查询复杂度。

数据库文件位置：`~/.config/nebulashare/intel.db`

### 2.2 表结构

```sql
-- 信息源：每种信息源一条记录
CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- 显示名称，如 "Hacker News"、"Hermes 播报"
    type TEXT NOT NULL CHECK(type IN ('hermes', 'rss', 'manual')),
    url TEXT,                        -- RSS URL 或 Hermes 目录路径
    config TEXT,                     -- JSON 额外配置
    is_active BOOLEAN DEFAULT 1,
    last_fetch_at TEXT,              -- ISO 8601
    last_error TEXT,                 -- 最近一次错误信息
    error_count INTEGER DEFAULT 0,   -- 连续失败次数
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 文章：所有来源统一结构存储
CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    external_id TEXT,                -- 来源侧唯一标识（RSS 的 guid、Hermes 的 URL 等）
    title TEXT NOT NULL,
    summary TEXT,                    -- 摘要/简介
    content TEXT,                    -- 完整内容（HTML 或 Markdown）
    url TEXT,                        -- 原文链接
    author TEXT,
    published_at TEXT,               -- ISO 8601，原始发布时间
    category TEXT,                   -- 固定分类（见 2.3）
    is_read BOOLEAN DEFAULT 0,
    is_starred BOOLEAN DEFAULT 0,
    is_archived BOOLEAN DEFAULT 0,
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);

-- 标签
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#3b82f6'     -- HEX 颜色值
);

-- 文章-标签多对多关联
CREATE TABLE article_tags (
    article_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (article_id, tag_id),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- 创建索引优化常用查询
CREATE INDEX idx_articles_source ON articles(source_id);
CREATE INDEX idx_articles_category ON articles(category);
CREATE INDEX idx_articles_published ON articles(published_at DESC);
CREATE INDEX idx_articles_starred ON articles(is_starred) WHERE is_starred = 1;
CREATE INDEX idx_articles_archived ON articles(is_archived) WHERE is_archived = 0;
```

### 2.3 固定分类（6 个）

| 分类 | 涵盖内容 |
|---|---|
| `AI` | 大模型、Agent、CV、NLP、AI 基础设施 |
| `互联网` | 科技新闻、产品更新、平台动态、开源项目 |
| `金融` | 股市、宏观经济、货币政策、财报 |
| `创投` | 融资、并购、创业动态、IPO |
| `工具` | 效率工具、开发者工具、SaaS、硬件 |
| `阅读` | 长文、深度报道、论文、技术博客 |

**分类来源：**
- Hermes 播报自带分类（AI、互联网、美股等），入库时映射到上表
- RSS 源可配置默认分类
- 手动录入时用户自选

### 2.4 预设标签（可选，用户可增删）

首批预设标签：
- `#必读`（红色 `#ef4444`）
- `#稍后读`（黄色 `#f59e0b`）
- `#项目参考`（蓝色 `#3b82f6`）
- `#投资相关`（绿色 `#22c55e`）

---

## 3. 采集层

### 3.1 Hermes 播报同步器

**输入：** `~/.hermes/daily-news/daily-news-YYYY-MM-DD.html`

**解析逻辑：**
1. 扫描目录，找出未入库的文件（按文件名日期判断）
2. 用 BeautifulSoup 解析 HTML 结构：
   - `.header .date` → 播报日期
   - `.section h2` → 分类名（映射到固定分类）
   - `.article` → 单篇文章：
     - `.source` → 来源网站
     - `.date` → 文章发布时间
     - `.title` + `href` → 标题 + 原文链接
     - `.summary` → 摘要
3. 每篇文章生成 `external_id = md5(url)` 去重
4. `source_id` 指向预置的 "Hermes 播报" 来源

**频率：** 每 10 分钟扫描一次（APScheduler）

### 3.2 RSS 采集器

**输入：** `sources` 表中 `type = 'rss'` 且 `is_active = 1` 的记录

**采集逻辑：**
1. 用 `feedparser` 拉取 RSS feed
2. 解析每个 entry：
   - `guid` / `id` → `external_id`
   - `title` → `title`
   - `summary` / `description` → `summary`
   - `link` → `url`
   - `published_parsed` → `published_at`
   - `author` → `author`
3. 增量采集：只拉取 `published_at > last_fetch_at` 的条目
4. 首次全量拉取最近 50 条

**频率：** 每 30 分钟一次（APScheduler）

**容错：**
- 单次失败 → `error_count += 1`，`last_error = 错误信息`
- 连续失败 3 次 → 自动将 `is_active` 设为 0，暂停采集
- 前端来源管理页面显示暂停状态，用户可手动恢复

### 3.3 手动录入

**入口：** 前端「新建文章」按钮

**方式 A：粘贴 URL**
1. 用户粘贴 URL
2. 后端用 `requests` + `BeautifulSoup` 抓取页面
3. 提取 `<title>`、`<meta name="description">`、`<article>` 或主要文本
4. 生成文章记录，用户可补充/修改标题、摘要、分类、标签

**方式 B：纯手动填写**
1. 用户填写标题、摘要、内容、分类
2. 内容支持 Markdown 格式
3. 可选填写原文链接

---

## 4. API 设计

### 4.1 文章

```
GET /api/intel/articles
  Query:
    - category?: string        按固定分类筛选
    - tag?: string             按标签名筛选
    - search?: string          全文搜索（标题、摘要、内容）
    - starred?: 1|0            只看收藏
    - unread?: 1|0             只看未读
    - archived?: 1|0           是否包含归档（默认 0，不含）
    - source_id?: number       按来源筛选
    - page?: number            默认 1
    - per_page?: number        默认 20，最大 100
  Response:
    { articles: [...], total: number, page: number, per_page: number }

GET /api/intel/articles/:id
  Response: 完整文章对象 + tags 数组

POST /api/intel/articles
  Body: { title, summary?, content?, url?, author?, category, tags?[], source_type: 'manual' }
  Response: 新建的文章对象

PUT /api/intel/articles/:id
  Body: { title?, summary?, content?, category?, is_read?, is_starred?, is_archived?, tags?[] }
  Response: 更新后的文章对象

DELETE /api/intel/articles/:id
  Response: { ok: true }
```

### 4.2 来源

```
GET /api/intel/sources
  Response: 来源列表（含文章数统计、最后同步时间、错误状态）

POST /api/intel/sources
  Body: { name, type: 'rss', url, category?, config? }
  Response: 新建的来源对象

PUT /api/intel/sources/:id
  Body: { name?, url?, category?, is_active?, config? }

DELETE /api/intel/sources/:id
  Response: { ok: true }
```

### 4.3 同步与标签

```
POST /api/intel/sync
  Body: { source?: 'hermes'|'rss'|'all' }   默认 'all'
  Response: { ok: true, synced: number, errors: number }
  说明：手动触发同步，异步执行，立即返回

GET /api/intel/tags
  Response: 标签列表（含使用次数统计）

POST /api/intel/tags
  Body: { name, color? }

DELETE /api/intel/tags/:id
  说明：删除标签，自动解除所有文章关联
```

### 4.4 统计

```
GET /api/intel/stats
  Response:
    {
      total_articles: number,
      unread_count: number,
      starred_count: number,
      category_breakdown: { AI: 12, 互联网: 34, ... },
      source_breakdown: [{ name, count }, ...],
      recent_activity: [{ date, read_count, added_count }, ...]  // 最近 7 天
    }
```

---

## 5. 前端设计

### 5.1 页面路由

| 路由 | 页面 | 说明 |
|---|---|---|
| `/intel` | 情报站主页 | 文章列表 + 阅读视图 + 搜索筛选 |
| `/intel/sources` | 来源管理 | 增删改 RSS 源、查看同步状态 |

### 5.2 主页布局（`/intel`）

```
┌─────────────────────────────────────────────────────────────┐
│  🔍 搜索...         [AI ▾] [互联网 ▾] [金融 ▾]  [⭐] [未读]   │
├────────────────────────────┬────────────────────────────────┤
│  📰 文章列表 (flex-1)       │  📖 阅读视图 (w-96 / drawer)    │
│  ━━━━━━━━━━━━━━━━━━━━      │                                │
│  ● 文章标题...        06-10 │  文章标题                       │
│  来源 · AI · #必读 #稍后读  │  ──────────────────             │
│                            │  摘要 / 正文内容                 │
│  ● 文章标题...        06-09 │                                │
│  来源 · 金融 · #投资相关    │  [已读] [⭐收藏] [标签+] [归档]  │
│                            │                                │
│  [加载更多...]              │                                │
│                            │                                │
└────────────────────────────┴────────────────────────────────┘
```

**列表项交互：**
- 点击 → 右侧打开阅读视图
- 悬停显示快捷操作：已读切换、收藏、标签
- 未读文章标题加粗，左侧有蓝色指示条
- 支持批量选择（Shift 连选、Ctrl 点选）

**阅读视图：**
- 顶部：标题、来源、发布时间、分类 pill、标签 pills
- 中部：正文内容（HTML 渲染或 Markdown 渲染）
- 底部操作栏：
  - 「标记已读/未读」
  - 「收藏/取消收藏」
  - 「添加标签」（弹出标签选择器）
  - 「归档」
  - 「在新标签页打开原文」（如有 url）

### 5.3 来源管理页面（`/intel/sources`）

```
┌─────────────────────────────────────────────┐
│  信息源管理                      [+ 新增源]  │
├─────────────────────────────────────────────┤
│  ┌───────────────────────────────────────┐  │
│  │ 📡 Hermes 播报                         │  │
│  │   类型: hermes | 文章: 328 | 状态: ✅   │  │
│  │   最后同步: 2 分钟前                    │  │
│  └───────────────────────────────────────┘  │
│  ┌───────────────────────────────────────┐  │
│  │ 📡 Hacker News                         │  │
│  │   类型: rss | 文章: 56 | 状态: ✅       │  │
│  │   最后同步: 15 分钟前                   │  │
│  │   [编辑] [暂停] [删除]                 │  │
│  └───────────────────────────────────────┘  │
│  ┌───────────────────────────────────────┐  │
│  │ 📡 某失效源                            │  │
│  │   类型: rss | 文章: 12 | 状态: ⚠️ 已暂停 │  │
│  │   最后同步: 3 天前 | 错误: 连接超时      │  │
│  │   [恢复] [编辑] [删除]                 │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

**新增 RSS 源表单：**
- 名称（输入）
- RSS URL（输入，后端验证可访问）
- 默认分类（下拉选择）
- 测试连接按钮

### 5.4 键盘快捷键

| 快捷键 | 功能 |
|---|---|
| `j` / `↓` | 下一篇文章 |
| `k` / `↑` | 上一篇文章 |
| `o` / `Enter` | 打开/关闭阅读视图 |
| `r` | 标记已读/未读 |
| `s` | 收藏/取消收藏 |
| `e` | 归档 |
| `t` | 添加标签（弹出选择器） |
| `?` | 显示快捷键帮助 |

### 5.5 新建文章弹窗（手动录入）

两种模式切换：
- **粘贴 URL：** URL 输入框 + 「抓取」按钮 → 自动填充标题/摘要 → 用户确认
- **手动撰写：** 标题、分类、标签、内容（Markdown 编辑器）、原文链接（可选）

---

## 6. 组件拆分

```
app/intel/
├── page.tsx                    # 主页面，布局容器
├── sources/
│   └── page.tsx                # 来源管理页面

components/intel/
├── article-list.tsx            # 文章列表
├── article-list-item.tsx       # 单条文章卡片
├── article-reader.tsx          # 阅读视图（右侧抽屉）
├── search-bar.tsx              # 搜索 + 筛选栏
├── category-filter.tsx         # 分类筛选 pills
├── tag-selector.tsx            # 标签选择/编辑弹窗
├── source-manager.tsx          # 来源管理列表
├── source-form.tsx             # 新增/编辑来源表单
├── article-form.tsx            # 手动录入弹窗
├── keyboard-help.tsx           # 快捷键帮助弹窗
├── sync-button.tsx             # 手动同步按钮 + 状态
└── stats-panel.tsx             # 统计面板（P2）
```

---

## 7. 错误处理

### 7.1 后端

| 场景 | 行为 |
|---|---|
| RSS 拉取失败 | `error_count++`，`last_error = 错误信息`，返回 200（不影响其他源） |
| RSS 连续 3 次失败 | 自动 `is_active = 0`，前端显示暂停状态 |
| Hermes HTML 解析失败 | 跳过该文件，记日志，继续处理其他文件 |
| URL 抓取失败（手动录入） | 返回 400 + 错误信息，前端提示用户手动填写 |
| 数据库操作失败 | 返回 500，Flask 记日志 |

### 7.2 前端

| 场景 | 行为 |
|---|---|
| API 请求失败 | Toast 提示，列表显示「加载失败，点击重试」 |
| 搜索无结果 | 显示空状态插画 + 「尝试其他关键词」提示 |
| 来源同步中 | 按钮显示 spinner，禁用重复点击 |

---

## 8. 定时任务（APScheduler）

```python
from flask_apscheduler import APScheduler

scheduler = APScheduler()

# Hermes 同步：每 10 分钟
@scheduler.task('interval', id='sync_hermes', minutes=10)
def sync_hermes_task():
    pass

# RSS 同步：每 30 分钟
@scheduler.task('interval', id='sync_rss', minutes=30)
def sync_rss_task():
    pass
```

启动方式：随 Flask 应用启动，单进程内执行。NebulaShare 目前是单进程 Flask，无需额外配置。

---

## 9. 实现阶段划分

### Phase 1：数据层 + Hermes 打通（P0）
- [ ] SQLite 数据库初始化（`init_intel_db()`）
- [ ] 数据模型工具函数（`db.py`）
- [ ] Hermes 同步器（解析 HTML，入库）
- [ ] 文章 API（列表、详情、更新已读/星标/归档）
- [ ] 前端：替换 mock，真实展示 Hermes 数据
- [ ] 前端：搜索、分类筛选、阅读视图

### Phase 2：手动录入 + 标签系统（P1）
- [ ] 标签 API（增删改查）
- [ ] 文章-标签关联
- [ ] 手动录入弹窗（URL 抓取 + 手动填写）
- [ ] 阅读视图内标签操作

### Phase 3：RSS 采集 + 来源管理（P1）
- [ ] RSS 采集器（feedparser）
- [ ] 来源 API（增删改查）
- [ ] 来源管理页面（`/intel/sources`）
- [ ] 手动同步按钮
- [ ] 来源错误状态展示

### Phase 4：增强功能（P2）
- [ ] 统计面板（`/api/intel/stats`）
- [ ] 键盘快捷键
- [ ] 导出功能（Markdown）
- [ ] 批量操作（批量已读、批量归档）

---

## 10. 与现有系统的兼容

| 现有功能 | 影响 | 处理方式 |
|---|---|---|
| `/api/daily-news` | 保留 | 但主页 Dashboard 的情报卡片改从 `/api/intel/articles` 拉取最新一条 |
| `/api/knowledge/graph` | 无直接影响 | 未来可扩展：情报站文章可一键加入知识图谱 |
| `/claude` 历史 | 无直接影响 | 不纳入情报站，保持独立模块 |
| 现有 `/intel` 路由 | 替换 | 内部组件完全替换，URL 不变 |

---

## 11. 技术栈确认

| 层面 | 技术 | 备注 |
|---|---|---|
| 数据库 | SQLite | 文件级，零运维 |
| ORM / DB 工具 | 手写 SQL + `sqlite3` 模块 | 项目无 ORM，保持轻量 |
| RSS 解析 | `feedparser` | 需新增依赖 |
| HTML 解析 | `beautifulsoup4` | 需新增依赖 |
| 定时任务 | `Flask-APScheduler` | 需新增依赖 |
| Markdown 渲染 | `react-markdown` | 前端需新增依赖 |
| 前端状态 | React useState | 暂不上 SWR，后续如需再引入 |

---

## 12. 自检记录

- **Placeholder 扫描：** 无 TBD、TODO、未定义项
- **内部一致性：** 分类体系（6 个固定分类）在数据层、API、前端保持一致
- **范围检查：** 本 spec 聚焦情报站，不涉及知识图谱改造、不改动其他模块核心逻辑
- **歧义检查：**
  - 「归档」= 从主列表隐藏，可通过筛选找回，不是删除 ✅
  - 「手动录入的 URL 抓取」= 后端执行，不是前端 CORS 绕过 ✅
  - 「全文搜索」= 搜索标题 + 摘要 + 内容，不匹配标签名（标签有独立筛选）✅
