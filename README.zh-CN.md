# Novel2Script Agent Studio

> 演示视频：[哔哩哔哩 72 小时 Demo 讲解](https://b23.tv/8aTHmco)
> 在线页面：[Netlify 项目页面](https://novel2script-agent-studio-lijiony.netlify.app/)
> YAML Schema 附件：[docs/schema.md](docs/schema.md)

语言：[English](README.md) | 简体中文

Novel2Script Agent Studio 是一个轻状态、无数据库的 AI 改编副编剧工作台。它帮助作者把 3 章以上小说文本改编成可表演、可编辑、可追踪的剧本 YAML 初稿。

项目不会一上来直接交最终 YAML，而是先理解小说、生成章节理解卡和改编计划，再让作者选择剧本类型、风格偏向、改编尺度、保留内容、禁止改动内容和备注，最后生成逐章剧本卡，并在作者确认后做连贯性合成。

后端使用固定 LangGraph 工作流，Pydantic v2 作为 Schema 唯一真源，结构化 JSON 经校验后由 `ruamel.yaml` 导出 YAML。前端提供任务式创作工作台、章节/剧本卡确认、YAML 编辑、校验和下载。

## 核心功能

- 支持粘贴小说文本或上传 `.txt` 文件。
- 少于 3 章会被后端拒绝。
- 先生成章节理解卡，展示摘要、人物、线索、冲突、情绪变化和改编机会。
- 作者可以逐章通过、重新理解、讨论修改。
- 通过章节理解后生成 Story Bible 和改编计划。
- 作者可以选择剧本类型、改编尺度、风格偏向、生成章节范围、保留内容、禁止改动和备注。
- 先生成每章剧本卡，再让作者逐章确认或重写。
- 所有剧本卡通过后做连贯性合成，导出 `script.json` 和 `script.yaml`。
- YAML 可在浏览器编辑，并可重新调用后端校验。
- 支持最终不满意返修：只重做连贯性、重写某章剧本卡，或两者一起修。
- 默认 mock 模式无需 API Key，也能稳定演示完整流程。

## 技术架构

```text
frontend/
  Next.js + React + TypeScript
  Monaco Editor + YAML validation fallback

backend/
  FastAPI
  LangGraph fixed workflow
  Pydantic v2 schema source of truth
  jsonschema semantic validation
  ruamel.yaml export

runs/{run_id}/
  Temporary run artifacts, no database
```

项目有意使用固定工作流，而不是自由 Agent。这样做的好处是输出更可追踪、更可复现，也更方便验证和演示。

## 快速启动

Windows 下推荐直接运行：

```powershell
.\scripts\start-demo.ps1
```

启动后打开：

```text
http://127.0.0.1:3000
```

开发模式：

```powershell
.\scripts\start-demo.ps1 -FrontendMode dev
```

停止服务：

```powershell
.\scripts\stop-demo.ps1
```

## 手动启动

后端：

```powershell
cd backend
uv venv
.venv\Scripts\Activate.ps1
uv pip install -e ".[dev]"
$env:USE_MOCK_LLM="true"
uvicorn app.main:app --reload --port 8000
```

前端：

```powershell
cd frontend
npm install
npm run dev:local
```

## 主要 API

| Method | Path | 作用 |
|---|---|---|
| `GET` | `/api/runs` | 获取本地 run 任务列表 |
| `POST` | `/api/runs/intake` | 创建 run，切章节并生成章节理解卡 |
| `GET` | `/api/runs/{run_id}/chapter-reviews` | 获取章节理解卡和审核状态 |
| `POST` | `/api/runs/{run_id}/chapter-cards/approve-all` | 通过全部章节理解卡 |
| `POST` | `/api/runs/{run_id}/build-plan` | 生成 Story Bible 和改编计划 |
| `POST` | `/api/runs/{run_id}/chapter-script-cards/generate` | 生成逐章剧本卡 |
| `GET` | `/api/runs/{run_id}/chapter-script-reviews` | 获取剧本卡和审核状态 |
| `POST` | `/api/runs/{run_id}/continuity-merge` | 合成最终剧本 JSON/YAML |
| `POST` | `/api/runs/{run_id}/final-feedback` | 提交最终不满意反馈 |
| `POST` | `/api/runs/{run_id}/final-confirm` | 确认最终剧本 |
| `GET` | `/api/runs/{run_id}/artifacts/{name}` | 下载产物 |
| `POST` | `/api/runs/{run_id}/validate-yaml` | 校验编辑后的 YAML |
| `GET` | `/api/schema/script` | 获取 Pydantic 生成的 JSON Schema |

## 测试

运行全部本地检查：

```powershell
.\scripts\check.ps1
```

后端测试：

```powershell
cd backend
.venv\Scripts\python -m pytest
```

前端构建：

```powershell
cd frontend
npm run build
```

前端 smoke test：

```powershell
cd frontend
npx playwright install chromium
npx playwright test
```

## 环境变量

后端：

- `USE_MOCK_LLM`：默认 `true`，无需 API Key 即可演示完整流程。
- `OPENAI_API_KEY`：真实模型模式下使用。
- `OPENAI_BASE_URL`：OpenAI-compatible API 地址。
- `OPENAI_MODEL`：模型名，默认 `gpt-4o-mini`。
- `RUNS_DIR`：run 产物目录，默认 `runs`。

前端：

- `NEXT_PUBLIC_API_BASE_URL`：默认 `http://127.0.0.1:8000`。

## YAML Schema

最终 YAML 的 Schema 由 Pydantic v2 模型定义，代码位置：

```text
backend/app/domain/schemas.py
```

后端接口：

```text
GET /api/schema/script
```

专门的 Schema 设计说明文档在：

[docs/schema.md](docs/schema.md)

这份文档解释了为什么 YAML 不只保存 `scene / action / dialogue`，还需要保存来源追踪、作者控制、改编理由、AI 新增内容、制作风险和修改建议。

## 样例输出

`samples/` 目录提供 mock 模式生成的静态样例：

- `samples/three_chapter_novel.txt`
- `samples/sample_adaptation_plan.md`
- `samples/sample_script.json`
- `samples/sample_script.yaml`
- `samples/sample_adaptation_report.md`

这些文件方便在不调用真实模型的情况下查看输出结构。

## 工作流

```text
validate_input
 -> parse_chapters
 -> read_chapters_individually
 -> await_chapter_review
 -> build_story_bible
 -> plan_adaptation
 -> await_author_controls
 -> generate_chapter_script_cards
 -> await_script_review
 -> continuity_merge
 -> generate_script_json
 -> validate_schema
 -> repair_once_if_needed
 -> export_yaml
 -> generate_report
```

作者可见的检查点包括：

1. 章节理解确认：系统生成章节理解卡，作者可以通过或重读。
2. 改编计划：系统基于通过的章节理解卡生成 Story Bible 和改编计划。
3. 剧本卡确认：系统根据作者控制项生成逐章剧本卡。
4. 连贯性合成：系统把已通过的剧本卡合成最终 `script.json` 和 `script.yaml`。
5. 最终确认/返修：作者可以确认结果，也可以把问题反馈回连贯性合成或某一章剧本卡。

## 原创部分

- 小说转剧本产品流程设计。
- Pydantic 剧本 Schema。
- 两阶段 LangGraph 改编副编剧工作流。
- 无数据库 run artifact 存储设计。
- YAML 导出和校验流程。
- 前端编辑、校验、下载和返修工作台。
- 示例文本和样例报告格式。

第三方依赖见 `backend/pyproject.toml` 和 `frontend/package.json`。

## 已知限制

- MVP 只支持纯文本和 `.txt` 输入。
- 长篇小说为了演示稳定性做了输入规模限制。
- Mock 模式输出偏稳定样例，真实质量取决于配置的模型。
- 真实模型模式需要自行配置 API Key，仓库不会保存密钥。
