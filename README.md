# Stock Sentinel - AI 驱动的市场情报哨兵

Stock Sentinel 是一个高度自动化、AI 驱动的美股市场情报监控与分析平台。它 7x24 小时不间断地聚合、分析、过滤和分发来自全球的金融新闻和市场数据，旨在为投资者提供**及时、精准、可行动的决策支持**。

通过集成强大的 AI 模型、多语言翻译引擎和灵活的报告系统，Stock Sentinel 将海量原始信息转化为结构化的中文投研内容，并通过 Discord 和专属的 Web 门户双重渠道触达用户。

![Hugo Web Portal](https://raw.githubusercontent.com/luka-z/stock-sentinel/main/docs/hugo_portal_showcase.png)

---

## 核心设计哲学

- **配置驱动**: 系统的所有行为，从新闻源到 AI 模型，均由少数几个 TOML 配置文件驱动，无需修改代码即可调整策略。
- **高度自动化**: 所有任务（新闻扫描、报告生成、市场监控）均由 Cron 调度，实现“一次部署，永久运行”。
- **AI 核心**: AI 不仅仅是辅助，更是整个情报流程的核心。从新闻筛选、翻译、总结到市场解读，AI 贯穿始终。
- **模块化代码**: `agent` 作为一个独立的 Python 包，内部模块职责分明，高度解耦，便于维护与扩展。

## 主要特性

- **可配置的新闻聚合**:
  - 在**单一配置文件 `settings.toml`** 中即可灵活接入包括 **RSS**、**Finnhub API** 在内的多种新闻源。
  - 每个新闻源均可独立配置其目标分发频道、最低处理评分和是否启用，实现精细化管理。

- **AI 赋能分析**:
  - **智能相关性评分**: 根据 `watch_list.toml` 中的标的，使用 LLM 对每条新闻进行 1-10 分的量化评估。
  - **AI 深度解析**: 对高分新闻，调用 **Gemini / Claude / NVIDIA** 等先进 LLM 进行深度翻译与摘要生成。

- **自动化报告与预警**:
  - 自动生成**美股早报**（盘前分析）和**美股晚报**（盘后总结、AI 解读）。
  - 实时监控自选股的价格和成交量异动。
  - AI 评分达标的新闻将作为“实时预警”即刻推送。

- **双重交付渠道**:
  - **Discord Bot**: 用于实时通知和警报。
  - **Hugo 静态站点**: 自动构建一个永久、可搜索的投研门户网站。

- **Ansible 自动化部署**:
  - 整套系统可通过 Ansible 脚本实现一键式、幂等的部署与更新。

## 项目结构

项目采用模块化的 Python 包结构，所有 agent 内的脚本都作为模块运行 (`python -m agent.xxx`)。

```
.
├── agent/                # 核心 Python Agent (作为包运行)
│   ├── __init__.py
│   ├── bot.py            # Discord Bot 主程序 (心跳服务)
│   ├── report.py         # 早/晚报生成器 (Cron)
│   ├── news_scanner.py   # 新闻扫描与 AI 评估 (Cron)
│   ├── market_scan.py    # 市场异动扫描器 (Cron)
│   ├── config.py         # 统一配置加载模块 (核心)
│   ├── data_engine.py    # 市场数据抓取引擎
│   ├── news_engine.py    # 新闻源抓取与去重引擎
│   ├── llm_gateway.py    # LLM API 统一网关
│   └── ...               # 其他辅助模块
├── config/               # 业务配置文件
│   ├── settings.toml     # !! 唯一的全局配置文件 !!
│   └── watch_list.toml   # 监控标的列表
├── data/                 # 数据存储目录 (自动创建)
│   └── sentinel.db       # SQLite 数据库
├── deploy/               # Ansible 部署脚本
└── hugo/                 # Hugo 站点源码
```

## 配置文件说明

为了简化管理，项目将绝大部分配置都整合到了唯一的 `settings.toml` 文件中。

### `config/settings.toml` (主文件)

这是系统的**单一事实来源 (Single Source of Truth)**，掌管几乎所有参数和密钥。

```toml
# ------------------ Discord ------------------
[discord]
report_channel_id = "..."
alert_channel_id = "..."

# ------------------ 调度任务 ------------------
[schedule]
cron_tz = "America/New_York"
morning_report = "07:30"

# ------------------ 新闻处理 ------------------
[news]
news_scan_interval_minutes = 15
relevance_threshold = 6 # AI 评分低于此值的新闻将被忽略

# 新闻源配置 (可添加多个)
[[news.sources]]
name             = "SEC 8-K 文件"
url              = "..."
type             = "rss"
enabled          = true
channel          = "notice"
min_score        = 0 # 0 表示无条件通过

[[news.sources]]
name             = "Yahoo Finance"
url              = "..."
type             = "rss"
enabled          = true
channel          = "alert"
min_score        = 6 # Yahoo 新闻只有 AI 评分 >=6 才会被推送

# ------------------ LLM 引擎 ------------------
[[llm.engines]]
name             = "gemini"
url              = "..."
priority         = 1
# ...
```

### `config/watch_list.toml` (标的列表)

定义 AI 评分和市场扫描的核心关注标的。

```toml
# 大盘指数（用于报告的宏观部分）
market_context = [
    { ticker = "SPY", name = "标普500" },
    { ticker = "QQQ", name = "纳指100" },
]

# 核心自选股（用于 AI 相关性分析和异动监控）
watch_list = [
    { ticker = "NVDA", name = "英伟达" },
    { ticker = "TSLA", name = "特斯拉" },
]
```
