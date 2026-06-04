# 90-second Demo Script

0-10s:
大家好，这是我的 XEngineer 第三批次作品 Novel2Script Agent Studio，选题是 AI 小说转剧本工具。它把三章以上小说转换成可编辑的 YAML 剧本初稿。

10-25s:
这里我加载一份三章小说示例。系统会把文本提交给后端，创建一次性的 run_id，不使用数据库。

25-45s:
点击开始改编后，可以看到固定 LangGraph 流水线依次执行：输入校验、章节解析、故事事实抽取、场景规划、剧本 JSON 生成、Schema 校验、YAML 导出和报告生成。

45-62s:
生成完成后，中间结果会保存为 `script.json`，程序再用 `ruamel.yaml` 导出 `script.yaml`。LLM 不直接输出 YAML，所以结构更稳定。

62-75s:
这里可以直接编辑 YAML，并通过后端重新校验。校验会检查 JSON Schema，也会检查角色引用、地点引用和章节覆盖。

75-88s:
右侧可以下载 YAML、Schema 文档和改编报告。README 顶部也放了 demo 视频链接、运行方式、依赖和原创部分说明。

88-90s:
这个 MVP 的重点是稳定完成三章小说到结构化剧本 YAML 的完整闭环。
