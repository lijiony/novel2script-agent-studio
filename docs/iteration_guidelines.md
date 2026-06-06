# Iteration And PR Guidelines

本规范用于 XEngineer 第三批项目迭代记录，重点保证提交过程清晰、连续、可复查。

第三批挑战窗口为中国时间 `2026-06-05 00:00` 至 `2026-06-07 23:59`。本项目所有有效开发提交应落在该时间窗口内，仓库与演示视频应从 `2026-06-08 00:00` 起保持公开可访问。

## 1. 基本原则

- 保持小步迭代：每次 commit 只表达一个明确变化。
- 新功能、明显修复、文档补充都通过 PR 记录过程。
- PR 合并后，`main` 分支必须仍然可以启动和验证。
- PR 描述必须和实际改动一致，不能留空，也不能只写“更新代码”。
- 不提交 `.env`、本地缓存、临时截图、运行产物或未授权素材。

## 2. Commit 规范

提交信息使用以下格式：

```text
<type>: <一句话说明本次改动>
```

推荐类型：

- `feat`: 新功能或用户可感知能力。
- `fix`: 缺陷修复。
- `docs`: README、说明文档、提交材料等。
- `test`: 测试用例或测试脚本。
- `refactor`: 不改变行为的结构调整。
- `chore`: 构建、依赖、脚本、工程维护。
- `ci`: 持续集成或自动检查配置。

示例：

```text
feat: 完成两阶段剧本生成流程
fix: 修复 YAML 校验失败时的状态展示
docs: 补充 XEngineer 提交检查清单
test: 增加三章节输入的接口测试
chore: 完善本地演示启动脚本
```

提交前建议自查：

- 本次 commit 是否只做一件事。
- 标题是否能让评审者不用打开代码就理解变化。
- 是否包含无关格式化、临时文件或密钥。

## 3. 分支规范

从 `main` 创建短生命周期分支，建议格式：

```text
codex/<日期>-<主题>
```

示例：

```text
codex/20260606-two-stage-workflow
codex/20260606-demo-hardening
codex/20260606-docs-final-check
```

一个分支对应一个清晰目标。若一个目标变大，应拆成多个 PR。

## 4. PR 规范

每个 PR 应尽量小而完整，标题建议沿用 commit 风格：

```text
feat: add two-stage adaptation planning workflow
fix: keep run status consistent after validation failure
docs: add final demo rehearsal guide
```

PR 描述必须包含：

- 本日进展：今天完成了哪些可运行、可验证的内容。
- 功能说明：这个 PR 为用户或评审者带来了什么。
- 实现方式：涉及的主要模块、核心逻辑、关键取舍。
- 验证方法：运行过哪些检查，或说明未运行的原因。
- 风险与后续：仍需补充、已知限制或下一步计划。

推荐 PR 描述模板：

```markdown
## 本日进展

- 完成：
- 调整：
- 待继续：

## Feature Description

Describe what this PR adds or changes and how a reviewer can use it.

## Implementation Approach

Describe the main technical decisions, modules touched, and any tradeoffs.

## Test Method

- [ ] Backend tests: `cd backend && .venv\Scripts\python -m pytest`
- [ ] Frontend build: `cd frontend && npm run build`
- [ ] Frontend smoke test: `cd frontend && npx playwright test`

## Risks And Follow-ups

- Known risks:
- Follow-ups:
```

## 5. 每日迭代流程

建议每天按以下顺序推进：

1. 从 `main` 同步最新代码并创建当天分支。
2. 先写清楚本轮目标，例如“完成输入分析流程”或“补齐提交材料”。
3. 按功能、修复、文档、测试拆分 commit。
4. 本地运行必要检查。
5. 发起 PR，并在 PR 描述中填写本日进展。
6. PR 通过检查后合并，确保 `main` 保持可运行。
7. 更新 README、演示脚本或提交清单中受到影响的内容。

## 6. 合并前检查

合并 PR 前至少确认：

- PR 标题和描述能准确说明改动。
- 本日进展写清楚，不只是文件列表。
- README 或 docs 已随行为变化更新。
- 本地检查结果已写入 PR。
- 没有提交 `.env`、密钥、本地运行目录或无关截图。
- `main` 合并后仍能按 README 启动。

## 7. 活动提交记录要求

XEngineer 评审会关注开发过程质量，因此仓库应体现：

- 连续、合理分布的 commit 记录。
- 多个单一目标 PR，而不是最后一天一次性导入。
- PR 描述与实际代码变化一致。
- README 顶部包含可访问的演示视频链接。
- 依赖、第三方库、原创部分和已知限制写清楚。

