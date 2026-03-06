# HebeIndex

田馥甄 (Hebe Tien) 影音内容索引 — 自动化收集、验证并展示田馥甄相关影音资源。

## 项目结构

```
hebeindex/
├── collector/   # Python AI Agent - 内容收集与验证
└── web/         # Astro + React 前端 - 内容展示
```

## Collector

基于 LLM 的智能内容收集器，通过 YouTube、Bilibili、Google 等平台搜索并验证田馥甄相关影音内容。

**功能：**
- 8 大分类、170+ 条搜索查询自动执行
- URL 可达性验证与去重
- 两种运行模式：Agent 模式（LLM 编排）/ Pipeline 模式（确定性流水线）
- 输出为结构化 JSON 和 Markdown 表格

**技术栈：** Python 3.13 / LiteLLM / YouTube Data API / Serper / Bilibili API

### 启动

```bash
cd collector
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env  # 填写 API keys
python pipeline.py    # Pipeline 模式
python agent.py       # Agent 模式
```

## Web

基于 Astro 的静态站点，展示收集到的影音索引，支持搜索与平台筛选。

**功能：**
- 分类浏览：MV / 演唱会 / 节目访谈 / 歌曲合作
- 模糊搜索（Fuse.js）
- 平台筛选（YouTube / Bilibili）
- 虚拟化长列表（TanStack Virtual）

**技术栈：** Astro 5 / React 19 / Tailwind CSS 4 / TypeScript

### 启动

```bash
cd web
pnpm install
pnpm dev
```

## 环境变量

参考 `collector/.env.example`，需要以下 API keys：

| 变量 | 用途 |
|------|------|
| `OPENROUTER_API_KEY` | LLM 调用（Claude / Gemini） |
| `YOUTUBE_API_KEY` | YouTube Data API v3 |
| `SERPER_API_KEY` | Google 搜索 |

## License

MIT
