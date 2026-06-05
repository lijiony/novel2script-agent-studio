"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { YamlEditor } from "@/components/YamlEditor";
import { ReportPanel } from "@/components/ReportPanel";
import {
  API_BASE_URL,
  AuthorControls,
  RunInfo,
  ValidationReport,
  artifactUrl,
  generateRun,
  getArtifact,
  getRun,
  getScriptSchema,
  intakeRun,
  validateYaml,
} from "@/lib/api";

const sampleText = `第一章 雨巷里的信

林夏在城南档案馆值夜班。傍晚的雨落在窄巷里，像有人把旧照片一张张翻过。她整理一箱无人认领的资料时，看见一封没有编号的信。信封上只有一句话：如果你还记得那盏灯，请在午夜前来旧剧院。

第二章 旧剧院的灯

旧剧院早已停用，门口的海报被雨水泡得褪色。林夏推门进去，舞台中央却亮着一盏孤零零的灯。灯下站着一个陌生老人，自称周砚，是父亲当年的舞台监督。

第三章 第三幕台词

林夏翻开旧剧本，发现第三幕的台词被人用铅笔改过。每一句台词的第一个字连起来，是城北钟楼的地址。她意识到父亲留下的不是谜题，而是一条求救路线。`;

const terminalStatuses = new Set(["succeeded", "failed_validation", "failed_llm", "failed_internal"]);

const defaultControls: AuthorControls = {
  format_type: "short_drama",
  adaptation_scale: "balanced",
  style_focus: "psychological",
  preserve_items: ["保留林夏、周砚和父亲失踪线索"],
  forbidden_changes: ["不要改变主角继续调查父亲失踪的核心动机"],
  author_notes: "心理活动尽量转成动作、停顿和克制对白。",
};

const formatOptions = [
  ["film", "影视剧本"],
  ["short_drama", "短剧"],
  ["stage_play", "舞台剧"],
  ["radio_drama", "广播剧"],
  ["animation", "动画"],
  ["game_script", "游戏脚本"],
] as const;

const scaleOptions = [
  ["faithful", "忠实版"],
  ["balanced", "平衡版"],
  ["bold", "大胆改编"],
] as const;

const focusOptions = [
  ["psychological", "心理外化"],
  ["action", "动作推进"],
  ["dialogue", "对白强化"],
  ["suspense", "悬疑节奏"],
  ["relationship", "关系冲突"],
  ["custom", "自定义"],
] as const;

export default function Home() {
  const [inputText, setInputText] = useState(sampleText);
  const [file, setFile] = useState<File | null>(null);
  const [run, setRun] = useState<RunInfo | null>(null);
  const [controls, setControls] = useState<AuthorControls>(defaultControls);
  const [planMarkdown, setPlanMarkdown] = useState("");
  const [yamlText, setYamlText] = useState("");
  const [reportMarkdown, setReportMarkdown] = useState("");
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null);
  const [schema, setSchema] = useState<Record<string, unknown> | null>(null);
  const [generationRequested, setGenerationRequested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canGenerate = Boolean(run?.run_id && run.status === "planned");
  const canValidate = Boolean(run?.run_id && yamlText.trim());
  const isPolling = Boolean(
    run && !terminalStatuses.has(run.status) && (run.status !== "planned" || generationRequested),
  );

  useEffect(() => {
    getScriptSchema()
      .then(setSchema)
      .catch(() => setSchema(null));
  }, []);

  useEffect(() => {
    if (!run || !isPolling) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const nextRun = await getRun(run.run_id);
        setRun(nextRun);
        if (nextRun.status === "planned") {
          await loadPlan(nextRun.run_id);
          setGenerationRequested(false);
        }
        if (nextRun.status === "succeeded") {
          await loadFinalArtifacts(nextRun.run_id);
          setGenerationRequested(false);
        }
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : String(nextError));
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [run, isPolling]);

  const artifactGroups = useMemo(() => {
    if (!run) {
      return [];
    }
    const workflowArtifacts = [
      "chapters.json",
      "reader_output.json",
      "planner_output.json",
      "adaptation_plan.json",
      "adaptation_plan.md",
      "author_controls.json",
    ].filter((artifact) => run.artifacts.includes(artifact));
    const deliverableArtifacts = [
      "script.json",
      "script.yaml",
      "schema.json",
      "schema.md",
      "adaptation_report.md",
      "report.json",
      "input.txt",
    ].filter((artifact) => run.artifacts.includes(artifact));
    const grouped = [...workflowArtifacts, ...deliverableArtifacts, "manifest.json"];
    const rest = run.artifacts.filter((artifact) => !grouped.includes(artifact));
    return [
      { title: "计划与中间产物", items: workflowArtifacts },
      { title: "最终交付产物", items: deliverableArtifacts },
      { title: "其他产物", items: rest },
    ].filter((group) => group.items.length > 0);
  }, [run]);

  async function handleIntake() {
    setBusy(true);
    setError(null);
    setPlanMarkdown("");
    setYamlText("");
    setReportMarkdown("");
    setValidationReport(null);
    setGenerationRequested(false);
    try {
      const nextRun = await intakeRun(inputText, file);
      setRun(nextRun);
      if (nextRun.status === "planned") {
        await loadPlan(nextRun.run_id);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerate() {
    if (!run) {
      return;
    }
    setBusy(true);
    setError(null);
    setYamlText("");
    setReportMarkdown("");
    setValidationReport(null);
    setGenerationRequested(true);
    try {
      const nextRun = await generateRun(run.run_id, controls);
      setRun(nextRun);
      if (nextRun.status === "succeeded") {
        await loadFinalArtifacts(nextRun.run_id);
        setGenerationRequested(false);
      }
    } catch (nextError) {
      setGenerationRequested(false);
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleValidateYaml() {
    if (!run) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const report = await validateYaml(run.run_id, yamlText);
      setValidationReport(report);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  function handleDownloadEditedYaml() {
    const blob = new Blob([yamlText], { type: "application/x-yaml;charset=utf-8" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "script.edited.yaml";
    anchor.click();
    window.URL.revokeObjectURL(url);
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;
    setFile(nextFile);
  }

  async function loadPlan(runId: string) {
    const plan = await getArtifact(runId, "adaptation_plan.md");
    setPlanMarkdown(plan);
  }

  async function loadFinalArtifacts(runId: string) {
    const [yaml, report] = await Promise.all([
      getArtifact(runId, "script.yaml"),
      getArtifact(runId, "adaptation_report.md"),
    ]);
    setYamlText(yaml);
    setReportMarkdown(report);
  }

  function updateControl<K extends keyof AuthorControls>(key: K, value: AuthorControls[K]) {
    setControls((current) => ({ ...current, [key]: value }));
  }

  function listFromText(value: string): string[] {
    return value
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  return (
    <div className="shell">
      <div className="topbar">
        <div className="brand">
          <h1>Novel2Script Agent Studio</h1>
          <p>AI 改编副编剧：先分析小说与改编计划，再生成可追踪 YAML 剧本。</p>
        </div>
        <a href={`${API_BASE_URL}/health`} target="_blank">
          API health
        </a>
      </div>

      <main className="main">
        <section className="panel">
          <header>
            <h2>输入与控制</h2>
          </header>
          <div className="panel-body">
            <textarea
              className="input-area"
              value={inputText}
              onChange={(event) => {
                setInputText(event.target.value);
                setFile(null);
              }}
              placeholder="粘贴至少三章小说文本..."
            />
            <div className="actions">
              <input accept=".txt" type="file" onChange={handleFile} />
              <button type="button" onClick={() => setInputText(sampleText)}>
                加载示例
              </button>
              <button type="button" disabled={busy || isPolling} onClick={handleIntake}>
                分析小说
              </button>
            </div>

            <div className="control-grid">
              <label>
                剧本类型
                <select
                  value={controls.format_type}
                  onChange={(event) =>
                    updateControl("format_type", event.target.value as AuthorControls["format_type"])
                  }
                >
                  {formatOptions.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                改编尺度
                <select
                  value={controls.adaptation_scale}
                  onChange={(event) =>
                    updateControl(
                      "adaptation_scale",
                      event.target.value as AuthorControls["adaptation_scale"],
                    )
                  }
                >
                  {scaleOptions.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                风格偏向
                <select
                  value={controls.style_focus}
                  onChange={(event) =>
                    updateControl("style_focus", event.target.value as AuthorControls["style_focus"])
                  }
                >
                  {focusOptions.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="field-block">
              必须保留
              <textarea
                value={controls.preserve_items.join("\n")}
                onChange={(event) => updateControl("preserve_items", listFromText(event.target.value))}
              />
            </label>
            <label className="field-block">
              禁止改动
              <textarea
                value={controls.forbidden_changes.join("\n")}
                onChange={(event) =>
                  updateControl("forbidden_changes", listFromText(event.target.value))
                }
              />
            </label>
            <label className="field-block">
              作者备注
              <textarea
                value={controls.author_notes ?? ""}
                onChange={(event) => updateControl("author_notes", event.target.value)}
              />
            </label>
            <div className="actions">
              <button type="button" disabled={!canGenerate || busy || isPolling} onClick={handleGenerate}>
                生成剧本
              </button>
            </div>
            {file ? <p className="notice">已选择文件：{file.name}</p> : null}
            {error ? <p className="error-text">{error}</p> : null}
          </div>
        </section>

        <section className="panel">
          <header>
            <h2>AI 改编计划</h2>
          </header>
          <div className="panel-body">
            {run ? (
              <div className="notice">
                run_id: <strong>{run.run_id}</strong>
                <br />
                状态：{run.status}
                {run.error ? <div className="error-text">{run.error}</div> : null}
              </div>
            ) : null}
            {planMarkdown ? (
              <div className="report plan-report">{planMarkdown}</div>
            ) : (
              <div className="notice">点击“分析小说”后，这里会显示章节检测、推荐方案和改编风险。</div>
            )}
            {run ? (
              <>
                <div className="status-list" style={{ marginTop: 10 }}>
                  {run.stages.map((stage) => (
                    <div className="stage" key={stage.name}>
                      <strong>{stage.name}</strong>
                      <span className={`badge ${stage.status}`}>{stage.status}</span>
                      {stage.message ? <small>{stage.message}</small> : null}
                    </div>
                  ))}
                </div>
                <div className="download-grid">
                  {artifactGroups.map((group) => (
                    <div className="download-group" key={group.title}>
                      <h3>{group.title}</h3>
                      {group.items.map((artifact) => (
                        <a key={artifact} href={artifactUrl(run.run_id, artifact)} target="_blank">
                          下载 {artifact}
                        </a>
                      ))}
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </div>
        </section>

        <section className="panel">
          <header>
            <h2>YAML 与报告</h2>
          </header>
          <div className="panel-body">
            {yamlText ? (
              <>
                <YamlEditor value={yamlText} schema={schema} onChange={setYamlText} />
                <div className="actions">
                  <button type="button" disabled={!canValidate || busy} onClick={handleValidateYaml}>
                    重新校验 YAML
                  </button>
                  <button type="button" disabled={!yamlText.trim()} onClick={handleDownloadEditedYaml}>
                    下载当前 YAML
                  </button>
                </div>
              </>
            ) : (
              <div className="notice">确认改编方向并生成后，这里会显示可编辑 YAML。</div>
            )}
            <div style={{ marginTop: 14 }}>
              <ReportPanel report={validationReport} markdown={reportMarkdown} />
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
