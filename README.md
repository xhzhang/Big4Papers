# SecAtlas · 网安四大会论文图谱

SecAtlas 是面向个人课程与讨论班选题的本地论文知识库，覆盖 IEEE S&P、ACM CCS、USENIX Security 和 NDSS。当前数据集完整收录 2023–2025 三个出版年度，并持续同步 2026 年官网已经公开的录用论文。

## 已实现

- 从 DBLP 对应会议卷发现论文全集，保留出版方/会议论文页面和 DOI；
- 从会议官网议程和出版卷提取官方 Session，并归一化为跨会议、跨年份的 Track；同时保存标准化输入、命中词、规则 ID、规则版本与确定性；
- 通过 OpenAlex 批量补充英文摘要与开放 PDF，并记录字段来源；
- 使用 SQLite 保存论文、作者、Topic、标签、来源和分析运行记录；
- 受控 Topic 体系，重点追踪智能手机安全、AIOS 安全、认证安全、智能体安全、AI 硬件安全和大模型安全；
- 对象、协议、技术、威胁和研究目标五类标签；
- H5 论文库，支持会议、年份、研究 Track、Topic、标签、标题、摘要和作者筛选；搜索按字段相关度排序，逐篇显示命中字段与证据片段，筛选状态可通过网址保存和分享；
- 2–3 篇论文结构化对比，统一查看对象、协议/技术、威胁/目标和摘要证据；达到上限后会明确提示，不会静默替换已有论文；
- Topic 年度时间线、共同作者团队线索、论文详情与讨论班清单；
- Web JSON、CSV 和飞书智能表格载荷导出；
- 独立的中文概述流程：只依据标题与英文摘要生成，不会改动已经校准的 Topic 和标签，并记录证据状态、生成来源、模型、提示版本与输入哈希。

## 本地部署与长期使用

日常运行只需要 Python 3.11+ 和 `requirements.txt` 中唯一的网页解析依赖。Node.js 22+ 与 pnpm 只在首次构建网页、或以后修改前端时使用，不需要作为日常运行服务常驻。

首次部署：

```powershell
python -m pip install -r requirements.txt
pnpm install
pnpm build
```

以后启动网站：

```powershell
.\scripts\start-local.ps1
```

浏览器打开 `http://localhost:3000/`。服务默认只监听本机 `127.0.0.1`，直接读取本地 SQLite 与静态网页，不依赖 GPT Sites、云数据库或外部后台。

网页数据采用三级静态分片：`public/catalog.json` 只保存约 40 个研究 Track 的规则证据、覆盖范围和分片清单；`public/catalog-papers/{year}.json` 保存年度论文列表、筛选字段和中文概述；`public/catalog-details/{year}.json` 保存英文摘要。首页优先载入当前选定年份或最新年份，先呈现可用论文，再并行补齐其余年度；搜索英文摘要、打开论文详情、对比或导出时才加载对应摘要。相同官方 Session 共用一条 Track 映射证据，避免在数千篇论文中重复存储。每次运行 Web 导出都会自动刷新清单和全部分片。

如果 3000 端口已被占用，也可以使用其他端口：

```powershell
python -m pipeline.server --port 8000
```

## 从网页更新论文数据

使用本地服务时，页面右上角会显示“更新数据”，它会运行固定、安全的本地更新流程。部署为 Vercel 等纯静态网站时该按钮自动隐藏，本地更新数据并重新构建后再推送即可：同步会议论文列表，补充官网摘要、PDF、Session 与 Track，分析新增论文，最后重新生成网页数据。更新期间可以继续浏览已有数据；同一时间只允许一个更新任务。

年份由系统自动决定。它会回补上一年，并尝试收集当前年份；如果中间多年没有运行，也会自动补齐缺少的年份。例如在 2027 年、现有数据到 2026 年时，点击后会刷新 2026 并尝试收集 2027。尚未公开的页面会被跳过并保留日志，不会因为某一个会议尚未发布列表而中断整个流程。

如需在命令行手动更新，仍可运行：

```powershell
.\scripts\update-catalog.ps1
```

采集适配器位于 `pipeline/sources/`。四个会议使用独立配置；未来官网结构变化时，只需维护对应采集器，无需改动数据库、分析或网页模块。
## 数据模型与可信度

本地数据库默认为 `data/papers.sqlite3`，运行时自动创建。主要实体包括：

- `papers`：论文事实字段、官方 Session、归一化 Track、摘要、概述和主 Topic；
- `authors` / `paper_authors`：作者及顺序；
- `paper_topics`：主 Topic、辅 Topic、置信度和分类版本；
- `tags` / `paper_tags`：类型化标签；
- `sources`：每个字段的提供者、来源 URL 和采集时间；
- `analysis_runs`：分析器、模型、提示词版本和原始结构化结果；
- `paper_relations`：为前作、后续、对比和扩展关系预留。

页面会明确区分事实字段、机器候选分类和缺失字段。论文详情中的“数据与 Track 溯源”会同时展示官网原始 Session、清洗后的规则输入、实际命中词、规则 ID、规则集版本和规则确定性；其中确定性描述规则具体程度，不是模型概率。规则分类只负责 Topic 与标签，不再生成或展示伪装成论文概述的模板文本；中文概述只有通过标题/摘要证据校验后才会进入网页与表格导出。

## 中文概述生成

中文概述与 Topic/标签分类是两条独立流程。生成器只读取论文标题和英文摘要，只更新概述字段；导入时会校验长度、证据状态和输入哈希，拒绝旧规则模板、过短结果、过期摘要对应的结果，以及没有声明证据限制的“仅标题”概述。

### 使用当前 ChatGPT 手工批处理

先把待生成论文拆成适合对话处理的小批次：

```powershell
python -m pipeline summarize-export --only-pending --batch-size 20 --output outputs/summary-batches
```

每个 `batch-xxxx.json` 已包含统一提示、标题、摘要、论文 ID 和输出格式。把一个批次交给 ChatGPT，把返回的 JSON 保存为同目录下的 `batch-xxxx.results.json`，再执行：

```powershell
python scripts/validate-summary-batches.py outputs/summary-batches
python -m pipeline summarize-import --input outputs/summary-batches --provider chatgpt-manual --model ChatGPT --strict
```

校验器会检查批次数量、顺序、论文 ID、输入哈希、证据状态、长度、数字线索和跨批次重复 ID。导入要求结果携带正确的 `input_hash`；重复导入同一批结果会安全跳过，不会重复追加分析记录。导入成功后会自动刷新 `public/catalog.json`。ChatGPT 网页/桌面订阅不能被本地脚本当作 API 批量调用，因此这个模式需要按批次处理；它适合当前人工抽检和逐步改善数据。

### 部署后使用 LLM API

配置一个兼容 Chat Completions JSON 契约的端点：

```powershell
$env:PAPER_SUMMARY_ENDPOINT="https://your-endpoint.example/v1/chat/completions"
$env:PAPER_SUMMARY_API_KEY="..."
$env:PAPER_SUMMARY_MODEL="your-model"
python -m pipeline summarize --only-pending --limit 20
```

先抽样检查 20 篇，确认质量后去掉 `--limit` 执行全量生成。配置这三个环境变量后，网页“更新数据”也会为新增或摘要发生变化的论文自动生成概述。项目使用标准库发起请求，不额外依赖厂商 SDK。
## 导出与飞书接口

```powershell
python -m pipeline export --format csv --output outputs/papers.csv
python -m pipeline export --format feishu-json --output outputs/feishu-records.json
```

`feishu-json` 已生成可映射到飞书多维表格的 `records[].fields` 结构，但一期不会主动调用飞书 API。后续只需新增认证和批量写入适配器，无需改动采集、分析或网页模块。

## 验证

```powershell
python -m unittest tests.test_pipeline
pnpm test
```

前者验证分类边界和 SQLite 往返；后者执行生产构建，并检查四会议覆盖、重点 Topic、数据规模和页面骨架。

## 数据来源策略

1. DBLP 会议卷用于发现完整的会议论文集合和标准化作者信息；
2. 会议官网议程与出版卷标题用于提取官方 Session；归一化 Track 去除场次编号和分段，并映射到约 40 个跨会议、跨年份的受控类别。只有研究型 Track 进入方向图谱；Poster、Demo、Workshop 等会议流程和 Miscellaneous 会保留用于追溯，但不会参与研究趋势统计；
3. DOI、出版方和会议页面作为权威论文落点；OpenAlex 用于补充摘要和开放访问 PDF；
4. PDF 只保存链接，不批量保存受版权保护的正文；
5. 团队页面仅显示共同作者算法线索，不把推断结果冒充机构或实验室事实。




