# 田馥甄（Hebe）内容收集 Agent

基于 Claude claude-opus-4-5 + tool_use，调用真实 API（YouTube Data API v3 / Serper.dev / Bilibili），
自动搜索并逐一验证链接，输出完整准确的 Markdown 资料库。

---

## 原理

```
Claude claude-opus-4-5
  ↓ tool_use 指令
  ├── youtube_search  → YouTube Data API v3（链接由官方 API 验证，100% 真实）
  ├── google_search   → Serper.dev Google 搜索（返回真实 URL）
  ├── bilibili_search → Bilibili 公开搜索接口（无需 key）
  ├── verify_urls     → httpx HEAD 请求，排除 404/无效链接
  └── write_file      → 写入 output/ 目录
```

---

## 第一步：申请 API Keys

### 1. Anthropic API Key
- 访问 https://console.anthropic.com/settings/keys
- 创建新 Key，复制备用

### 2. YouTube Data API v3（免费）
1. 访问 https://console.cloud.google.com
2. 创建新项目（任意名称）
3. 左侧导航 → API 和服务 → 库 → 搜索 "YouTube Data API v3" → 启用
4. 左侧导航 → API 和服务 → 凭据 → 创建凭据 → API 密钥
5. 复制生成的密钥（以 `AIza` 开头）

> 每日免费配额：10,000 units。一次搜索消耗 100 units，本 agent 约用 3000–5000 units，完全够用。

### 3. Serper.dev API Key（每月 2500 次免费）
1. 访问 https://serper.dev
2. 注册账号（Google 登录即可）
3. 注册后自动获得 2500 次免费额度
4. 在 Dashboard 复制 API Key

---

## 第二步：配置

```bash
cd collector

# 复制模板
cp .env.example .env

# 编辑 .env 填入三个 key
ANTHROPIC_API_KEY=sk-ant-...
YOUTUBE_API_KEY=AIza...
SERPER_API_KEY=...
```

---

## 第三步：安装依赖并运行

```bash
# 使用 uv（推荐）
uv venv
uv pip install -r requirements.txt
uv run python agent.py

# 或使用 pip
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python agent.py
```

### 断点续传

如果运行中断，可以从上次进度继续：

```bash
uv run python agent.py --resume
```

---

## 输出

运行结束后，`output/` 目录生成以下文件：

```
output/
├── README.md                        ← 总目录
├── 专辑与MV/
│   ├── 个人MV完整列表.md            ← 所有个人MV，含验证链接
│   └── 单曲与影视歌.md
├── 演唱会/
│   └── 演唱会视频.md
├── 综艺节目/
│   └── 综艺节目视频.md
├── 采访与访谈/
│   └── 采访视频.md
├── SHE相关/
│   └── SHE_MV与演出.md
└── 其他内容/
    └── 合唱与合作.md
```

---

## 运行时间与费用估算

| 项目 | 预估 |
|------|------|
| 运行时间 | 15–30 分钟 |
| Claude API 费用 | ~$1–3（claude-opus-4-5，约 500K tokens）|
| YouTube API | 免费（配额内）|
| Serper.dev | 免费（2500次配额内）|
| Bilibili | 免费 |

---

## 日志

- 实时日志输出到终端
- 完整日志保存到 `agent_run.log`
- 运行进度保存到 `.checkpoint.json`（用于断点续传，成功完成后自动删除）

---

## 链接准确性保证

| 来源 | 验证方式 | 准确性 |
|------|---------|-------|
| YouTube Data API | 官方 API 直接返回，不存在的视频不会出现 | ✅ 100% |
| Bilibili 搜索 | verify_urls HTTP 检查，status 200 才写入 | ✅ 已验证 |
| Google 搜索结果 | verify_urls HTTP 检查 | ✅ 已验证 |
| 超时/无法确认 | 写入文件但标注 ⚠️ | ⚠️ 请人工确认 |
| 404/无效 | 直接丢弃，不写入文件 | — |
