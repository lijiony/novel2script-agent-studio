"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { YamlEditor } from "@/components/YamlEditor";
import { ReportPanel } from "@/components/ReportPanel";
import {
  API_BASE_URL,
  RunInfo,
  ValidationReport,
  artifactUrl,
  createRun,
  getArtifact,
  getRun,
  getScriptSchema,
  validateYaml,
} from "@/lib/api";

const sampleText = `第一章 雨巷里的信

林夏在城南档案馆值夜班。傍晚的雨落在窄巷里，像有人把旧照片一张张翻过。她整理一箱无人认领的资料时，看见一封没有编号的信。信封上只有一句话：如果你还记得那盏灯，请在午夜前来旧剧院。

第二章 旧剧院的灯

旧剧院早已停用，门口的海报被雨水泡得褪色。林夏推门进去，舞台中央却亮着一盏孤零零的灯。灯下站着一个陌生老人，自称周砚，是父亲当年的舞台监督。

第三章 第三幕台词

林夏翻开旧剧本，发现第三幕的台词被人用铅笔改过。每一句台词的第一个字连起来，是城北钟楼的地址。她意识到父亲留下的不是谜题，而是一条求救路线。`;

const doneStatuses = new Set(["succeeded", "failed_validation", "failed_llm", "failed_internal"]);

export default function Home() {
  const [inputText, setInputText] = useState(sampleText);
  const [file, setFile] = useState<File | null>(null);
  const [run, setRun] = useState<RunInfo | null>(null);
  const [yamlText, setYamlText] = useState("");
  const [reportMarkdown, setReportMarkdown] = useState("");
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null);
  const [schema, setSchema] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canValidate = Boolean(run?.run_id && yamlText.trim());
  const isRunning = Boolean(run && !doneStatuses.has(run.status));

  useEffect(() => {
    getScriptSchema()
      .then(setSchema)
      .catch(() => setSchema(null));
  }, []);

  useEffect(() => {
    if (!run || doneStatuses.has(run.status)) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const nextRun = await getRun(run.run_id);
        setRun(nextRun);
        if (nextRun.status === "succeeded") {
          const [yaml, report] = await Promise.all([
            getArtifact(nextRun.run_id, "script.yaml"),
            getArtifact(nextRun.run_id, "adaptation_report.md"),
          ]);
          setYamlText(yaml);
          setReportMarkdown(report);
        }
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : String(nextError));
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [run]);

  const artifactLinks = useMemo(() => {
    if (!run) {
      return [];
    }
    const preferredOrder = [
      "chapters.json",
      "reader_output.json",
      "planner_output.json",
      "script.json",
      "script.yaml",
      "schema.json",
      "schema.md",
      "adaptation_report.md",
      "report.json",
      "input.txt",
    ];
    const ordered = preferredOrder.filter((artifact) => run.artifacts.includes(artifact));
    const rest = run.artifacts.filter(
      (artifact) => artifact !== "manifest.json" && !ordered.includes(artifact),
    );
    return [...ordered, ...rest];
  }, [run]);

  async function handleCreateRun() {
    setBusy(true);
    setError(null);
    setYamlText("");
    setReportMarkdown("");
    setValidationReport(null);
    try {
      const nextRun = await createRun(inputText, file);
      setRun(nextRun);
    } catch (nextError) {
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

  return (
    <div className="shell">
      <div className="topbar">
        <div className="brand">
          <h1>Novel2Script Agent Studio</h1>
          <p>固定 LangGraph 流水线，将 3 章以上小说转换为可编辑 YAML 剧本。</p>
        </div>
        <a href={`${API_BASE_URL}/health`} target="_blank">
          API health
        </a>
      </div>

      <main className="main">
        <section className="panel">
          <header>
            <h2>小说输入</h2>
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
              <button type="button" disabled={busy || isRunning} onClick={handleCreateRun}>
                {isRunning ? "生成中" : "开始改编"}
              </button>
            </div>
            {file ? <p className="notice">已选择文件：{file.name}</p> : null}
            {error ? <p className="error-text">{error}</p> : null}
          </div>
        </section>

        <section className="panel">
          <header>
            <h2>YAML 剧本编辑器</h2>
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
              <div className="notice">生成完成后，这里会显示可编辑 YAML。</div>
            )}
          </div>
        </section>

        <section className="panel">
          <header>
            <h2>流程与报告</h2>
          </header>
          <div className="panel-body">
            {run ? (
              <>
                <div className="notice">
                  run_id: <strong>{run.run_id}</strong>
                  <br />
                  状态：{run.status}
                  {run.error ? <div className="error-text">{run.error}</div> : null}
                </div>
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
                  {artifactLinks.map((artifact) => (
                    <a key={artifact} href={artifactUrl(run.run_id, artifact)} target="_blank">
                      下载 {artifact}
                    </a>
                  ))}
                </div>
              </>
            ) : (
              <div className="notice">创建 run 后，这里会显示 LangGraph 节点进度。</div>
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
