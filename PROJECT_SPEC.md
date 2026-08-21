# A股每日复盘页面 — 技术说明文档

> **文档目的**：供协作者（人类 / AI 助手）快速理解本项目的架构、数据流、页面结构、部署机制与扩展方式，以便参与开发与维护。
>
> **线上地址**：https://liaohao.cc/stock-a/ （收盘版） / https://liaohao.cc/stock-a/午盘/ （午间版）
>
> **项目路径**：`/Users/sugieliao/WorkBuddy/A股每日复盘/`
>
> **最后更新**：2026-08-21

---

## 一、项目概述

这是一个 A 股每日收盘复盘页面，每个交易日自动采集市场数据、渲染为单页 HTML 报告、部署到 Cloudflare Pages。页面包含 8 个模块，覆盖市场宽度、指数走势、板块成交、资金流向、RPS 共振、个股排名、新高新低、涨跌停清单。页面支持 hover 迷你 K 线弹窗、图表缩放、午间/收盘双版本切换。

**核心设计原则**：
- **多数据源、自动降级**：每个模块有主源和备用源，主源失败时自动切换，页面显示占位提示而非崩溃。
- **双部署模式**：静态 HTML（自包含，离线可看）+ 动态页（运行时 fetch JSON bundle，更新只需重传小文件）。
- **涨红跌绿**：遵循中国 A 股配色约定——红色 = 涨，绿色 = 跌。
- **不构成投资建议**：页面底部声明「仅客观复盘，不构成投资建议」。

---

## 二、架构总览

```
┌─────────────────────────────────────────────────────────┐
│                     数据采集层（Python）                   │
│  collect_hithink.py    → 市场宽度/指数/板块成交/个股         │
│  collect_sectors_ths.py → 板块三(成交额) + 板块四(主力净流入) │
│  collect_sector_rps.py  → 板块五(RPS共振)                  │
│  collect_wande.py       → 平均股价(880003)日K              │
│  collect_jzxt.py        → 均线占用率(市场宽度·均占系统)      │
│  collect_tdx_hl.py      → 个股新高/新低(通达信)            │
│  build_classify.py      → 个股→行业/概念分类映射(缓存<7天)  │
├─────────────────────────────────────────────────────────┤
│                     渲染层（render.py）                     │
│  读取 data/{date}_*.json → 生成 A股复盘_{date}.html        │
│  同时输出 data/{date}_close_bundle.json (动态页用)         │
│  同时输出 data/manifest_close.json (manifest)             │
├─────────────────────────────────────────────────────────┤
│                     部署层（Cloudflare Pages）              │
│  daily_pipeline.py      → 采集+渲染+质量闸门+wrangler部署   │
│  deploy_light_pos.py    → 仅重发（不重新采集/渲染）         │
│  静态页 → stock-a/index.html (收盘)                        │
│  静态页 → stock-a/午盘/index.html (午间)                   │
│  动态页 → stock-a/dyn/ (收盘) / dyn/午盘/ (午间)           │
│  Pages Functions → /api/kline, /api/trigger, /api/status  │
└─────────────────────────────────────────────────────────┘
```

### 双部署模式详解

**静态页（Path B）**：
- `render.py` 直接把数据内联到 HTML 的 `<script>const D = {...}</script>` 中
- 完全自包含，离线可看，但每次更新需重新生成整个 HTML
- 部署到 `stock-a/index.html`（收盘）/ `stock-a/午盘/index.html`（午间）

**动态页（Path A）**：
- 外壳 `app.html` + 运行时 `fetch('manifest.json')` → `fetch(bundle.json)` → 注入 DOM + JS
- 更新只需重新上传小的 bundle JSON（几百 KB），外壳和 JS 不变
- `extract_dyn.py` 从静态 HTML 中抽取图表逻辑（`chartlogic.js`）和控制逻辑（`ctrl.js`），去掉 `const D=...` 首句
- 两种模式同日渲染结果完全一致，只是数据加载时机不同（编译时 vs 运行时）

---

## 三、数据源与对应模块

| 模块 | 数据源 | 采集脚本 | 输出文件 | 鉴权 |
|------|--------|----------|----------|------|
| 一、市场表现 | 同花顺 hithink-finance REST | `collect_hithink.py` | `{date}_hithink.json` | API Key（`~/.workbuddy/hithink_finance_key`） |
| 一、平均股价 | 通达信 pytdx 直连 | `collect_wande.py` | `wande.json` | 无 |
| 一、均线占用率 | 均占系统 ghxb.site | `collect_jzxt.py` | `jzxt_history.json` | Bearer Token（`data/.jzxt_token`） |
| 二、宽基指数 | 同花顺 hithink | 同上 hithink | 同上 | 同上 |
| 二、风格指数 | 同花顺 tszs / 腾讯 | 同上 hithink | 同上 | 同上 |
| 三、板块成交额 | 同花顺 AKShare 行业 | `collect_sectors_ths.py` | `{date}_sectors_ths.json` | 无（AKShare 公开接口） |
| 四、主力净流入 | 同花顺 AKShare 行业 | 同上 | 同上 | 无 |
| 五、RPS 共振 | 通达信 pytdx（主）+ 同花顺（备） | `collect_sector_rps.py` | `sector_rps.json` | 无 |
| 六、个股排名 | 同花顺 hithink | 同上 hithink | 同上 | 同上 |
| 七、新高/新低 | 通达信 tdx_screener（当日）/ 腾讯 westock（T-1 兜底） | `collect_tdx_hl.py` | `{date}_tdxhl.json` / `{date}_westock.json` | 无 |
| 八、涨跌停 | 同花顺 hithink 快照 | 同上 hithink | 同上 | 同上 |
| hover K线 (个股) | 腾讯 ifzq.gtimg.cn fqkline | `functions/api/kline.js`（Pages Function） | 实时 | 无 |
| hover K线 (板块) | 东方财富 push2his（**注意见下方已知问题**） | 同上 | 实时 | 无 |

### 关键约束
- **东方财富 push2/push2his 对当前 IP 被封锁**（2026-08-21 起），用户明确要求不再使用东财作为采集源。`functions/api/kline.js` 中的板块 hover K 线仍走东财（因为是浏览器端 Cloudflare 边缘请求，IP 不同），但采集层已完全弃用东财。
- **同花顺与通达信的 881xxx 代码体系完全不兼容**：同花顺 881124 = 消费电子，TDX 881124 = 粮油加工。采集层各模块各自使用对应数据源的代码体系，互不混用。

---

## 四、页面结构（8 大模块）

### 模块一：市场表现
- **KPI 卡片**：全 A 等权涨跌幅、涨跌幅中位数、总成交额、上涨/下跌/平、涨停/跌停
- **4 张历史曲线**（近 60 交易日）：
  - 总成交额（亿元）
  - 涨跌家数（红涨绿跌双线）
  - 涨停/跌停家数
  - 个股创新高/新低家数
- **平均股价(880003) 日K**：通达信等权全 A 代理，用 candlePlugin 在 Chart.js 折线图上叠加 K 线柱
- **均线占用率（市场宽度）**：来自均占系统，5 日/13 日/50 日/120 日均线占用率，带 zonePlugin 叠加极冰/冰点/中枢/过热/高潮参考线

### 模块二：指数表现
- **宽基指数表**：上证/深证/创业板/科创50/沪深300/中证500/中证1000/上证50
- **宽基指数归一化曲线**（近 60 交易日，首日=100）：用 `idxNorm` 将绝对点位归一化，消除指数间量级差异
- **风格指数表 + 曲线**：全A/创历史新高/昨日成交前10/微盘股/北证50/北交所昨日涨停/昨日涨停

### 模块三：成交量排名前 10 板块
- **数据源**：同花顺 AKShare `stock_board_industry_summary_ths()` — 90 个同花顺行业
- **表格**：序号 / 板块名 / 成交额(亿) / 成交额占比% / 涨跌幅
- **图表**：成交额柱状图 + 成交额占比%折线叠加
- **hover K线**：每行可悬停显示该板块近 60 日收盘走势迷你 K 线（数据来自 `{date}_sectors_ths.json` 中的 `hist_dates` / `hist_close`）
- **板块名 hover 属性**：`sa_attr(code, sector=True)` 生成 `class="sa-hover" data-code="{code}" data-hist-key="sec:{code}"`

### 模块四：主力净流入板块
- **数据源**：同花顺 AKShare 行业（与模块三同源、同口径）
- **双栏表格**：主力净流入 TOP10（红）/ 主力净流出 TOP10（绿）
- **图表**：净流入前 10 板块柱状图
- **与模块三对照**：同一套 90 行业口径，可直接对照同一行业的成交额与资金流向

### 模块五：强势板块 RPS 共振
- **数据源**：通达信 pytdx `get_index_bars(4, 1, '881xxx', 0, n)` — TDX 概念板块指数
- **RPS 定义**：`RPS(N) = (1 - rank/N_total) × 100`，即板块 N 日涨幅在流动性预筛后板块集合中的排名百分位
- **筛选条件**：5/10/20/50 日 RPS 中至少 3 个 > 87
- **流动性预筛选**：按成交额降序保留前 65%，至少保留 150 个
- **表格**：板块名 / 类别 / RPS5 / RPS10 / RPS20 / RPS50 / 达标周期数
- **图表**：横向分组条形图（前 25 个通过板块，最弱在下），4 个 RPS 周期并列
- **板块名解析**（四级）：实时 `get_security_list` → 缓存 `tdx_concept_names.json` → 补丁表 `tdx_concept_names_patch.json` → code 兜底
- **名称 hover**：与模块三相同的 hover K 线机制，优先用页面已嵌入的 `hist_close`

### 模块六：成交量排名前 100 个股
- **数据源**：同花顺 hithink-finance
- **表格**：序号 / 名称 / 代码 / 成交额(亿) / 涨跌幅 / 行业 / 概念板块
- **51-100 行默认折叠**，点击展开；排序时折叠行一并参与
- **行业/概念**：来自 `build_classify.py` 生成的 `stock_classify.json`（缓存 < 7 天才重建）

### 模块七：个股新高/新低
- **数据源**：通达信 tdx_screener 当日条件选股（优先）/ 腾讯 westock T-1 兜底
- **KPI**：创一年新高家数 / 创一年新低家数
- **清单表格**：名称 / 代码 / 涨跌幅 / 行业 / 概念板块

### 模块八：涨停/跌停个股
- **数据源**：同花顺 hithink 快照
- **KPI**：涨停家数 / 跌停家数
- **清单表格**：名称 / 代码 / 涨跌幅 / 成交额 / 行业 / 概念板块

---

## 五、关键文件清单

### 核心脚本
| 文件 | 职责 |
|------|------|
| `render.py` | 渲染引擎：读取 data/ 下所有 JSON → 生成 A股复盘_{date}.html + bundle + manifest |
| `collect_hithink.py` | 同花顺 hithink REST 采集（市场/指数/板块/个股/涨跌停） |
| `collect_sectors_ths.py` | 同花顺 AKShare 90 行业采集（板块三成交额 + 板块四主力净流入 + 60日K线） |
| `collect_sector_rps.py` | RPS 共振计算（TDX 概念板块指数，5/10/20/50日，阈值87） |
| `collect_wande.py` | 平均股价(880003) 日K（pytdx 直连） |
| `collect_jzxt.py` | 均占系统均线占用率（ghxb.site，Bearer 鉴权） |
| `collect_tdx_hl.py` | 个股新高/新低（通达信 tdx_screener 条件选股） |
| `build_classify.py` | 个股→行业/概念分类映射（缓存 < 7 天重建） |
| `daily_pipeline.py` | 日常流水线：采集→渲染→质量闸门→wrangler 部署 |
| `deploy_light_pos.py` | 轻量重发布：只暂存+部署，不重新采集/渲染 |
| `extract_dyn.py` | 从静态 HTML 抽取 chartlogic.js + ctrl.js 供动态页使用 |
| `app.html` | 动态页外壳：运行时 fetch manifest→bundle→注入 DOM |

### Cloudflare Pages Functions
| 文件 | 职责 |
|------|------|
| `functions/api/kline.js` | hover 迷你 K 线 API：个股→腾讯 fqkline，板块→东方财富 push2his |
| `functions/api/trigger.js` | 按钮触发 API：转发到本机隧道服务触发抽数/通达信量化 |
| `functions/api/status.js` | 红绿灯状态 API：转发到本机隧道服务获取抽数状态 |

### 数据文件命名规则
| 文件名模式 | 说明 |
|------------|------|
| `{date}_hithink.json` | 同花顺 hithink 当日采集结果 |
| `{date}_sectors_ths.json` | 同花顺 90 行业当日采集（板块三+四） |
| `{date}_tdxhl.json` | 通达信新高/新低当日选股结果 |
| `{date}_westock.json` | 腾讯 westock 兜底数据 |
| `{date}_close_bundle.json` | 收盘版动态页 bundle（payload + body_html + meta） |
| `{date}_midday_bundle.json` | 午间版动态页 bundle |
| `manifest_close.json` | 收盘版 manifest（指向最新 bundle） |
| `manifest_midday.json` | 午间版 manifest |
| `sector_rps.json` | RPS 共振结果（最新，不按日期） |
| `wande.json` | 平均股价日K（最新，不按日期） |
| `jzxt_history.json` | 均线占用率日线（最新，不按日期） |
| `stock_classify.json` | 个股→行业/概念映射（缓存<7天重建） |
| `tdx_concept_names.json` | TDX 板块名缓存（744条） |
| `tdx_concept_names_patch.json` | TDX 板块名补丁表（302条，人工核验） |
| `tdx_concept_names_full.json` | TDX 板块名全量扫描缓存（323条，live截断名） |
| `name_map.json` | 同花顺全量股票名称映射（~5550只，2天重建） |
| `ths_clid_cache.json` | 同花顺板块 clid 缓存（备用源用） |
| `.jzxt_token` | 均占系统 Bearer Token（不进代码/日志） |

### 配置与密钥
| 文件 | 说明 |
|------|------|
| `secrets.env` | `CF_TOKEN=xxx`（Cloudflare API Token）、`CF_ACCOUNT=xxx` |
| `~/.workbuddy/hithink_finance_key` | 同花顺 hithink API Key（600权限） |
| `data/.jzxt_token` | 均占系统 Bearer Token |
| `.pipeline.lock` | flock 互斥锁文件（防并发流水线） |
| `CNAME` | Cloudflare Pages 自定义域名配置（liaohao.cc） |
| `.nojekyll` | 禁用 GitHub Pages Jekyll 处理 |

---

## 六、数据流水线

### 日常流水线 `daily_pipeline.py`
```
1. 采集（同日）：
   - collect_hithink.py {date}           → 市场宽度/指数/板块成交/个股
   - collect_sectors_ths.py {date}       → 板块三/四（同花顺90行业）
   - collect_sector_rps.py               → RPS 共振（仅收盘版；午间版跳过，沿用上一交易日）
   - collect_wande.py {date}             → 平均股价日K
   - collect_jzxt.py                     → 均线占用率
   - build_classify.py                   → 个股分类映射（缓存<7天跳过）

2. 渲染：
   - python3 render.py {date} [--midday] → A股复盘_{date}.html + bundle + manifest
   - hithink 当日文件缺失则跳过渲染

3. 质量闸门：
   - hithink 市场数据非空 ✓
   - sectors_ths 前10非空 ✓
   - HTML 生成成功 ✓
   - 三项全通过才允许发布

4. 发布：
   - 读 secrets.env → CF_TOKEN
   - 无 token 时只生成本地报告，绝不触碰线上（安全）
   - wrangler pages deploy /tmp/cfpub --project-name=stock-a
   - 静态页 → stock-a/index.html（收盘）/ stock-a/午盘/index.html（午间）
   - 动态页 → stock-a/dyn/（收盘）/ dyn/午盘/（午间）
   - functions/ → 同步部署
```

**互斥锁**：`fcntl.flock(LOCK_EX | LOCK_NB)` — 午间/收盘/轮询共享同一套 data 与部署目录，同一时刻只允许一个实例运行。锁在进程退出/崩溃后自动释放。

### 轻量重发布 `deploy_light_pos.py`
```
1. 暂存（不采集/渲染）：
   - 复制已存在的 A股复盘_{date}.html → /tmp/cfpub/stock-a/index.html
   - 复制 A股午盘_{date}.html → /tmp/cfpub/stock-a/午盘/index.html（如存在）
   - stage_dyn：app.html + chartlogic.js + ctrl.js + manifest + bundle → dyn/ 子树
   - functions/ → 同步

2. 部署：
   - wrangler pages deploy /tmp/cfpub
```

用法：`python3 deploy_light_pos.py [YYYY-MM-DD]` — 用于修复后快速重发，不重跑采集。

---

## 七、hover 迷你 K 线机制

### 触发方式
表格中带 `class="sa-hover"` 的单元格，鼠标悬停 300ms 后弹出迷你 K 线弹窗（420×340px）。

### 数据获取优先级
1. **页面已嵌入的历史数据**（`data-hist-key` 属性）：
   - 板块：`sec:{code}` → 从 `D.rps.passed` / `D.top_sectors` / `D.net_inflow_sectors` 中查找 `hist_dates` / `hist_close`
   - 指数：`{code}` → 从 `D.indices` / `D.style_indices` 中查找
   - 找到则直接用 Canvas 绘制折线图（无 OHLC 时画折线，有时画 K 线柱）
2. **API 请求**（页面无嵌入数据时）：
   - `GET /api/kline?code={code}&mkt={mkt}&lmt=60` → Cloudflare Pages Function
   - 个股 → 腾讯 `ifzq.gtimg.cn/appstock/app/fqkline/get`（前复权日K）
   - 板块 → 东方财富 `push2his.eastmoney.com`（`secid=90.881xxx`）

### 弹窗渲染
- Canvas 2D 手绘 K 线/折线，非 Chart.js
- 涨红跌绿（`#d8392b` / `#16a34a`）
- 显示末点数值、首尾日期、数据来源标注

### `sa_attr()` 函数（render.py L179-199）
```python
def sa_attr(code, sector=False):
    # 板块代码（88开头6位）→ data-hist-key="sec:{code}"
    # 个股代码（600519.SH 等）→ data-code + data-mkt
    # 纯数字 → 自动推断市场（6开头=sh, 0/3开头=sz, 920开头=bj）
```

---

## 八、动态页加载流程（app.html）

```
1. fetch('manifest.json', {cache:'no-store'})
   → { bundle: "data/2026-08-21_close_bundle.json", generated: "..." }

2. fetch(manifest.bundle, {cache:'no-store'})
   → { meta: {report_date, pagemode}, body_html: "...", payload: {...} }

3. wrap.innerHTML = bundle.body_html
   → 注入页面 DOM 结构（但 <script> 不执行）

4. fetch('chartlogic.js?v={generated}', {cache:'no-store'})
   → 图表/图例/缩放/排序逻辑（从静态 HTML 抽取，已去掉 const D=... 首句）

5. fetch('ctrl.js?v={generated}', {cache:'no-store'})
   → 控制按钮逻辑（saTrigger / reextractCheck / pollStatus / initSaHover）

6. var D = bundle.payload;
   var s = document.createElement('script');
   s.textContent = 'var D = ' + JSON.stringify(b.payload) + ';\n' + chartlogic + '\n' + ctrl;
   document.body.appendChild(s);
   → 合并注入，执行全部图表渲染 + 交互逻辑
```

**缓存击穿**：`?v={generated}` 参数避免浏览器/边缘缓存旧的 chartlogic.js / ctrl.js 导致修复不生效。

---

## 九、已知问题与修复记录

### 1. 板块三/四 hover K 线数据错误（已修复 2026-08-21）
- **根因**：`collect_sectors_ths.py` 旧版用 thsdk 获取同花顺行业代码（881124=消费电子），然后用 TDX `get_index_bars('881124')` 取 K 线，但 TDX 的 881124 = 粮油加工，代码体系不兼容。
- **修复**：重写 `collect_sectors_ths.py`，改用 AKShare `stock_board_industry_index_ths(symbol=行业名称)` 获取与名称严格对应的 K 线。实时数据用 `stock_board_industry_summary_ths()`。
- **影响范围**：所有自引入 TDX K 线（约 8/13 起）的历史 `sectors_ths.json` 中的 `hist_close` 可能错误。批量重跑新版即可覆盖。

### 2. RPS 板块 881019 缺名（已修复 2026-08-21）
- **根因**：TDX 公共服务器 `get_security_list` 对 88xxx 有固定上限（~323 个），881019 不在返回名单内。
- **修复**：建 `tdx_concept_names_patch.json`（302 条人工核验名称），收集器增加补丁分支。四级解析：实时列表→缓存→补丁表→code 兜底。
- **881019 = 化纤**（881018 化妆品→881019 化纤→881020 涤纶 链），用 15 只化纤股等权涨幅实证自洽。

### 3. 板块名截断问题（已修复 2026-08-21）
- **根因**：TDX live 服务器返回的名称字段截断到 9 字节（~4 汉字），如「印刷包装」实际是「印刷包装机械」。
- **修复规则**：live 名是文档全名的截断前缀时→用文档全名；同为 4 字的真实名称冲突→保持 live 名（TDX 自身显示名更权威）。

### 4. 东财 push2 被封（已知限制）
- **影响**：采集层已完全弃用东财。`functions/api/kline.js` 中板块 hover K 线仍走东财（浏览器端边缘请求，IP 不同），如果东财对 Cloudflare IP 也封了，板块 hover K 线将无法弹出。个股 hover K 线走腾讯，不受影响。
- **备选方案**：板块 hover 已嵌入页面数据（`hist_dates`/`hist_close`），不依赖 API。API 只在页面无嵌入数据时才调用。

---

## 十、Python 环境与依赖

| 运行时 | 路径 | 用途 |
|--------|------|------|
| 系统 Python 3.9.6 | `/usr/bin/python3` | `render.py`、`daily_pipeline.py`（调子脚本）、`build_classify.py` |
| 托管 Python 3.13.12 venv | `/Users/sugieliao/.workbuddy/binaries/python/envs/default/bin/python` | `collect_sectors_ths.py`（需要 akshare）、`collect_sector_rps.py`（需要 pytdx）、`collect_wande.py`、`deploy_light_pos.py` |
| Node.js 22.22.2 | `/Users/sugieliao/.workbuddy/binaries/node/versions/22.22.2/bin/node` | wrangler 部署 |

**venv 依赖**：`akshare`、`pytdx`、`thsdk`（可选，游客模式经常连不上）

**wrangler 预装路径**：`/Users/sugieliao/.workbuddy/binaries/node/workspace/node_modules/wrangler/bin/wrangler.js` — 避免 `npx` 每次临时拉取导致 ENOTEMPTY 竞态。

---

## 十一、扩展指南

### 新增一个数据模块
1. 写 `collect_{name}.py`，输出 `data/{date}_{name}.json`
2. 在 `render.py` 的 `load()` 函数中读取该 JSON 并合并到 `d` 字典
3. 在 `build_html()` 中添加 HTML 模板块（`<div class="card">...</div>`）
4. 在 `payload` 字典中添加需要传给前端 JS 的数据
5. 如需图表，在 `<script>` 部分用 `makeChart()` 创建 Chart.js 实例
6. 在 `daily_pipeline.py` 的采集阶段添加 `run([PY, "collect_{name}.py", date], "label")`
7. 在质量闸门中添加检查项（可选）
8. 运行 `python3 render.py {date}` 验证本地渲染
9. 运行 `python3 deploy_light_pos.py {date}` 部署

### 新增一个 hover K 线数据源
1. 在 `functions/api/kline.js` 的 `onRequest()` 中添加新的分支判断
2. 实现 `fetch{name}Kline(code, lmt)` 函数
3. 在前端 `showKlineTip()` 中，如果 `histKey` 命中页面嵌入数据则直接用，否则走 API

### 修改页面样式
- 样式集中在 `render.py` 的 `<style>` 块和 `app.html` 的 `<style>` 块中
- **两处必须同步修改**（静态页和动态页外壳）
- 关键 CSS 变量：`RED="#d8392b"`、`GREEN="#16a34a"`、`GREY="#888"`

### 修改图表逻辑
- 图表逻辑在 `render.py` 的 `<script>` 块中（`makeChart`、`lineCfg`、`barCfg` 等）
- 修改后需重新 `render.py` 生成新 HTML，`extract_dyn.py` 会自动抽取到 `chartlogic.js`
- 动态页通过 `?v={generated}` 参数缓存击穿，用户无需手动刷新

---

## 十二、自动化调度

当前通过定时任务触发 `daily_pipeline.py`：

| 时间 | 任务 | 说明 |
|------|------|------|
| 交易日 11:45 | `python3 daily_pipeline.py --midday` | 午间版（渲染午盘 HTML，部署到 /午盘/） |
| 交易日 15:47 | `python3 daily_pipeline.py` | 收盘版（完整采集+渲染+部署到根 /） |
| 每小时 | reextract 轮询 | 通过队列触发重新抽数（jsonbin 队列） |

**周末处理**：自动回退到最近周五日期。

**通达信量化任务**：页面上的「通达信量化」按钮通过 `functions/api/trigger.js` 转发到本机隧道服务，触发 Parallels VM 中的通达信 GUI 自动化（4 个串行任务 task1-task4，状态文件 gate 串接）。

---

## 十三、配色约定（重要）

| 含义 | 颜色 | Hex |
|------|------|-----|
| 涨 / 正值 / 高 / 强势 | 红色 | `#d8392b` |
| 跌 / 负值 / 低 / 弱势 | 绿色 | `#16a34a` |
| 中性 / 平 / 占位 | 灰色 | `#888` |
| 主色（标题/链接/强调） | 蓝色 | `#2b6cb0` |
| 提示 / 注释 | 琥珀色 | `#b7791f` |

这是中国 A 股市场约定（涨红跌绿），与美股/欧股约定相反，**全局不可搞反**。

---

## 十四、目录结构

```
A股每日复盘/
├── render.py                  # 渲染引擎
├── daily_pipeline.py          # 日常流水线
├── deploy_light_pos.py        # 轻量重发布
├── extract_dyn.py             # 静态→动态 JS 抽取
├── collect_hithink.py         # 同花顺 hithink 采集
├── collect_sectors_ths.py      # 同花顺 AKShare 90行业采集
├── collect_sector_rps.py      # RPS 共振计算
├── collect_wande.py           # 平均股价日K
├── collect_jzxt.py            # 均占系统均线占用率
├── collect_tdx_hl.py          # 通达信新高/新低
├── build_classify.py          # 个股分类映射
├── app.html                   # 动态页外壳
├── secrets.env                # Cloudflare 密钥
├── CNAME                      # 自定义域名
├── .nojekyll
├── .pipeline.lock             # flock 互斥锁
├── vendor/
│   └── chart.umd.min.js       # Chart.js 离线副本
├── web/
│   └── chart.umd.min.js       # 动态页用 Chart.js 副本
├── functions/
│   └── api/
│       ├── kline.js           # hover K线 API
│       ├── trigger.js         # 按钮触发 API
│       └── status.js          # 红绿灯状态 API
├── data/                      # 所有数据文件
│   ├── {date}_hithink.json
│   ├── {date}_sectors_ths.json
│   ├── {date}_tdxhl.json
│   ├── {date}_westock.json
│   ├── {date}_close_bundle.json
│   ├── {date}_midday_bundle.json
│   ├── manifest_close.json
│   ├── manifest_midday.json
│   ├── sector_rps.json
│   ├── wande.json
│   ├── jzxt_history.json
│   ├── stock_classify.json
│   ├── tdx_concept_names.json
│   ├── tdx_concept_names_patch.json
│   ├── tdx_concept_names_full.json
│   ├── name_map.json
│   ├── ths_clid_cache.json
│   └── .jzxt_token
├── A股复盘_{date}.html         # 收盘版静态 HTML
├── A股午盘_{date}.html         # 午间版静态 HTML
└── README.md                  # 索引页（每日追加一行）
```

---

## 十五、给协作者的快速上手

### 本地调试
```bash
# 1. 采集某日数据（需要 venv 里的 akshare/pytdx）
/Users/sugieliao/.workbuddy/binaries/python/envs/default/bin/python collect_sectors_ths.py 2026-08-21

# 2. 渲染 HTML
python3 render.py 2026-08-21
# 或午间版
python3 render.py 2026-08-21 --midday

# 3. 本地打开验证
open A股复盘_2026-08-21.html

# 4. 部署（需要 secrets.env 里的 CF_TOKEN）
/Users/sugieliao/.workbuddy/binaries/python/envs/default/bin/python deploy_light_pos.py 2026-08-21

# 5. 完整流水线（采集+渲染+部署）
python3 daily_pipeline.py 2026-08-21          # 收盘版
python3 daily_pipeline.py --midday 2026-08-21  # 午间版
python3 daily_pipeline.py --no-deploy 2026-08-21  # 只本地不发布
```

### 常见排障
| 症状 | 可能原因 | 解决 |
|------|----------|------|
| 板块名显示为代码 | TDX 服务器未返回该名称 | 检查 `tdx_concept_names_patch.json` 是否有该 code |
| 板块 hover K 线不弹出 | 页面无嵌入数据 + API 失败 | 检查 `hist_close` 是否在 JSON 中；检查东财是否被封 |
| 图表不渲染 | Chart.js 未加载 | 检查 `vendor/chart.umd.min.js` 是否存在 |
| 部署失败 | CF_TOKEN 无效 | 检查 `secrets.env` |
| 流水线跳过 | 另一实例正在运行 | 检查 `.pipeline.lock` 是否被占用（flock 自动释放） |
| hithink 采集失败 | API Key 过期 | 检查 `~/.workbuddy/hithink_finance_key` |
| 均占系统无数据 | Token 过期 | 更新 `data/.jzxt_token` |

### 修改前的检查清单
- [ ] 修改 `render.py` 后是否也同步了 `app.html` 的样式？
- [ ] 新增的数据 JSON 是否在 `render.py` 的 `load()` 中读取？
- [ ] 新增的采集脚本是否在 `daily_pipeline.py` 中注册？
- [ ] 修改图表逻辑后是否重新 `render.py` 以更新 `chartlogic.js`？
- [ ] 涨跌颜色是否正确（涨红跌绿，不可搞反）？
- [ ] 部署前是否先本地 `open` 验证渲染结果？

---

*本文档由项目维护者编写，供协作者参考。如有疑问或发现过时信息，请联系项目维护者更新。*
