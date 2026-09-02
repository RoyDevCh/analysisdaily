# analysisdaily — 中立客观日报系统

一个端到端的“中立客观日报”管道：多源摄取 → 事件聚类 → 事实交叉核验与偏见分析 → 结构化日报生成 → 分发。

> 目标：把同一事件的多个来源报道，聚合成**单一事件**，用**最大公约数事实 + 左右翼分歧/盲区分析**生成**中立、可追溯**的日报条目。

## 分层架构（对应用户给定设计）

| 层 | 本仓库模块 | 说明 |
|----|-----------|------|
| 1. 多源数据摄取 | `src/analysisdaily/ingestion` | 电讯社/光谱/背景四类通道，可插拔适配器 |
| 2. 预处理与事件聚类 | `src/analysisdaily/clustering` | 文本向量化 + 24h 滑动窗口 HDBSCAN → Event_Cluster_ID |
| 3. 事实交叉核验与偏见分析 | `src/analysisdaily/facts` | 最大公约数事实 / 左右翼分歧+盲区 / 情绪形容词剥离；LLM 可选，规则兜底 |
| 4. 结构化日报生成 | `src/analysisdaily/synthesis` | Pydantic 严格 Schema 校验 + 引用追溯 + JSON/Markdown 渲染 |
| 5. 编排调度与分发 | `src/analysisdaily/orchestration, delivery` | CLI + 每日调度 + 多终端输出 |

## 三道防幻觉护城河
1. **禁止开放式生成**：所有输出走 Pydantic 严格 Schema，字段仅允许事实陈述。
2. **强制引文接地**：每条事实携带 `quote_span` 原文证据；无证据的句子在后处理剔除。
3. **来源可信度权重**：电讯社(center/center-left/center-right)最高权重用于定基调；分析/评论类低权重仅用于归纳分歧。

## 快速开始
```bash
# 1. 建虚拟环境并安装
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"

# 2. 启动 PostgreSQL + pgvector（可选，默认可用本地文件/内存后端）
docker compose up -d

# 3. 用离线样本跑通全管道（无需网络/无密钥）
python -m analysisdaily --fixture data/e2e_sample --out data/reports

# 4. 用公开 RSS 跑真实数据（需要网络）
python -m analysisdaily --run --date 2026-09-02
```

## 配置
复制 `.env.example` 为 `.env`。所有密钥都是可选的：系统无 LLM/无外部 API 也能以规则引擎离线运行。

## 引导说明
- 无任何外部凭据也能跑通（规则引擎 + 公开 RSS/样本夹具）。
- 接真实 Ground News / Reuters / AP / OWID：在 `ingestion` 的对应适配器填 key 即可，接口已预留。
- 接 LLM 事实引擎：设置 `LLM_*_API_KEY` 并在 `facts` 引擎开启 `provider=llm`。

## 真实数据与数据质量说明

**指令正确入口**：`python -m analysisdaily`（等价 CLI），子任务用 `--fixture` / `--run`。

本 MVP 用**公开 RSS** 打通链路，已实测可拉到真实文章（Reuters/AP/BBC/Pew via 公开 RSS）。
因公开 RSS 是"按来源/栏目"推送、题材混杂，实时 `--run` 可能产生少量噪声事件
（例如单一来源的错合并、样本过少无法判定光谱分歧）。因此：

- **离线可复现**：用 `--fixture data/e2e_sample`，样本夹具已控好左右中光谱与多源共分母，
  演示效果最干净（2 个事件、各 5 条接地事实、分歧与盲区提示完整）。
- **高质量实时**：接入真实官方/授权源。在 `ingestion/sources.py` 用**主题级** Google News 查询
  （同一事件多源覆盖）替代"来源级"查询，或填 `GROUND_NEWS_API_KEY` /
  `ALLSIDES_API_KEY` / `WIRE_EARTH_API_KEY` 启用预留的 API 适配器
  （`ingestion/adapters.py` 的 `GroundNewsAdapter` / `AllSidesAdapter` / `WireApiAdapter`）。

## 工程护城河实现（对照需求"四、防御幻觉与偏见"）

| 护城河 | 落地位置 | 说明 |
|--------|----------|------|
| 禁止开放式生成 | `models/report.py` | Pydantic 严格 Schema；headline/fact 禁感叹号与情绪词硬校验 |
| 强制引文接地 | `facts/extractor.py` + `models/report.py` | 每条事实强制 ≥1 个 QuoteSpan；无证据事件在 `synthesis/builder.py` 拒绝生成 |
| 来源可信度权重 | `models/report.py` BiasLabel `fact_weight` | Center 最高、极端源仅用于分歧归纳；`weighted_texts` 按权重排序 |
| 情绪/形容词剥离 | `facts/subjectivity.py` | 规则化剔除煽动词与推测句 |
| 事件聚类 | `clustering/clusterer.py` | 24h 滑动窗口 + 平均连接抗链式聚类（可选 HDBSCAN） |
| 盲区计算 | `facts/divergence.py` | 按左右翼/源覆盖占比判定单侧回避 |
## LLM 事实引擎（Ollama Cloud gemma4:31b）

把 `.env` 的 `LLM_PROVIDER` 设为 `openai`（Ollama Cloud 走 OpenAI 兼容接口），并填：
`LLM_BASE_URL=https://ollama.com/v1`、`LLM_API_KEY=<你的 key>`、`LLM_MODEL=gemma4:31b`。

开启后，`facts/llm_engine.py` 将：
- 用**严格 JSON 提示**约束模型输出事实与左右翼侧重（temperature=0.1，防开放式生成）；
- **证据 quote_span 由真实抓取文本回填** —— 模型只给"事实文本+来源名"，引文绝不来自模型凭空捏造；
- **任一失败自动回退规则引擎**（engine=rules），保证日报永远可生成。

## 本地 PostgreSQL/pgvector 容器

已提供 `docker-compose.yml`（镜像 `pgvector/pgvector:pg16`，端口映射 5433）。启动：

```bash
docker compose up -d          # 首次会拉镜像；需要 Docker 守护进程在运行
pip install -e ".[db]"        # 安装 psycopg 以便真正写库
python -m analysisdaily --run # 之后运行会自动把文章/日报写入 Postgres（未启动时自动跳过）
```

## 分发（邮件 / Telegram / Notion）

在 `.env` 配置对应项，`dispatch` 会在生成日报后在**已配置**渠道推送，未配置自动跳过：
- 邮件 SMTP：`SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_TO`
- Telegram：`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
- Notion：`NOTION_TOKEN` / `NOTION_DATABASE_ID`

## GitHub Actions 每日定时

`.github/workflows/daily.yml`：每天 UTC 00:00（北京 08:00）跑实时管道并上传产物。
在仓库 **Settings → Secrets → Actions** 配置对应 `LLM_*`、`SMTP_*`、`TELEGRAM_*`、
`NOTION_*` 等 secret；空 secret 也能跑（自动落在规则引擎 + 公开 RSS 兜底）。
若把 `COMMIT_REPORT` secret 设为 `true`，会把生成结果 commit 回仓库存档。
