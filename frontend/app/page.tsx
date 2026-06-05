"use client";

import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import { YamlEditor } from "@/components/YamlEditor";
import { ReportPanel } from "@/components/ReportPanel";
import {
  API_BASE_URL,
  AuthorControls,
  ChapterCard,
  ChapterReviewItem,
  LlmStatus,
  LlmTestResult,
  RunListItem,
  RunInfo,
  ValidationReport,
  approveAllChapters,
  approveChapter,
  artifactUrl,
  buildPlan,
  generateRun,
  getArtifact,
  getChapterChatMessages,
  getChapterReviews,
  getLlmStatus,
  getRun,
  getScriptSchema,
  intakeRun,
  listRuns,
  regenerateChapter,
  testLlmConnection,
  validateYaml,
} from "@/lib/api";

type ArtifactPanel = "chapterCards" | "storyBible" | "yaml" | "report" | "downloads" | "details";
type ConversationPhase = "idle" | "analyzing" | "reviewing" | "planned" | "generating" | "completed" | "failed";
type ReviewFilter = "all" | "pending" | "attention";

type StoryBible = {
  main_plot: string;
  character_arcs: string[];
  relationship_map: string[];
  timeline: string[];
  major_clues: string[];
  adaptation_risks: string[];
  recommended_generation_scope: number[];
  chapter_index: Array<{
    chapter_id: string;
    title: string;
    char_count: number;
    summary: string;
  }>;
};

type ScenePlan = {
  id: string;
  title: string;
  source_chapters: number[];
  dramatic_purpose: string;
  key_events: string[];
  conflict: string;
  emotional_shift: string;
  source_excerpt: string;
  source_function: string;
  adaptation_treatment: string;
  adaptation_reason: string;
  performance_notes: string;
  risk_note: string;
};

type AdaptationRisk = {
  severity: "info" | "warning" | "error";
  target: string;
  message: string;
  suggestion: string;
};

type AdaptationPlan = {
  summary: string;
  chapter_count: number;
  recommended_format_type: AuthorControls["format_type"];
  recommended_style_focus: AuthorControls["style_focus"];
  recommended_adaptation_scale: AuthorControls["adaptation_scale"];
  recommended_generation_scope: number[];
  rationale: string[];
  format_rationale: string[];
  technical_notes: string[];
  character_notes: string[];
  plot_threads: string[];
  scene_plan: ScenePlan[];
  risks: AdaptationRisk[];
};

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

const stepLabels = [
  "小说输入",
  "章节确认",
  "作者确认",
  "剧本生成",
  "YAML 打磨",
];

export default function Home() {
  const [inputText, setInputText] = useState(sampleText);
  const [file, setFile] = useState<File | null>(null);
  const [tasks, setTasks] = useState<RunListItem[]>([]);
  const [run, setRun] = useState<RunInfo | null>(null);
  const [controls, setControls] = useState<AuthorControls>(defaultControls);
  const [planMarkdown, setPlanMarkdown] = useState("");
  const [adaptationPlan, setAdaptationPlan] = useState<AdaptationPlan | null>(null);
  const [chapterCards, setChapterCards] = useState<ChapterCard[]>([]);
  const [chapterReviews, setChapterReviews] = useState<ChapterReviewItem[]>([]);
  const [reviewsExpanded, setReviewsExpanded] = useState(false);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("all");
  const [openChapterId, setOpenChapterId] = useState<string | null>(null);
  const [chatChapterId, setChatChapterId] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<Array<{ role: "user" | "assistant"; content: string }>>([]);
  const [assistantDraft, setAssistantDraft] = useState("");
  const [visibleThinking, setVisibleThinking] = useState("");
  const [toolEvents, setToolEvents] = useState<string[]>([]);
  const [typedSummaries, setTypedSummaries] = useState<Record<string, string>>({});
  const [storyBible, setStoryBible] = useState<StoryBible | null>(null);
  const [storyBibleMarkdown, setStoryBibleMarkdown] = useState("");
  const [yamlText, setYamlText] = useState("");
  const [reportMarkdown, setReportMarkdown] = useState("");
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null);
  const [schema, setSchema] = useState<Record<string, unknown> | null>(null);
  const [llmStatus, setLlmStatus] = useState<LlmStatus | null>(null);
  const [llmTestResult, setLlmTestResult] = useState<LlmTestResult | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activeArtifactPanel, setActiveArtifactPanel] = useState<ArtifactPanel | null>(null);
  const [generationRequested, setGenerationRequested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allChaptersApproved = chapterReviews.length > 0
    && chapterReviews.every((item) => item.review.status === "approved" && item.card);
  const canBuildPlan = Boolean(run?.run_id && run.status === "awaiting_chapter_review" && allChaptersApproved);
  const canGenerate = Boolean(run?.run_id && run.status === "planned");
  const canValidate = Boolean(run?.run_id && yamlText.trim());
  const isPolling = Boolean(
    run
      && (
        (!terminalStatuses.has(run.status) && !["awaiting_chapter_review", "planned"].includes(run.status))
        || generationRequested
      ),
  );
  const phase = getConversationPhase(run, isPolling, generationRequested, error, yamlText);
  const fallbackPlan = useMemo(() => parsePlanMarkdown(planMarkdown), [planMarkdown]);
  const hasArtifacts = Boolean(run?.artifacts.length);
  const completed = phase === "completed";
  const totalChapterChars = chapterCards.reduce((sum, card) => sum + card.char_count, 0);
  const activeChatChapter = chapterReviews.find((item) => item.review.chapter_id === chatChapterId) ?? null;
  const sidePanelOpen = Boolean(chatChapterId || activeArtifactPanel);

  useEffect(() => {
    getScriptSchema()
      .then(setSchema)
      .catch(() => setSchema(null));
    refreshLlmStatus();
    refreshTasks();
  }, []);

  useEffect(() => {
    if (!run || !isPolling) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const nextRun = await getRun(run.run_id);
        setRun(nextRun);
        await refreshTasks();
        if (
          nextRun.status === "reading_chapters"
          || nextRun.status === "awaiting_chapter_review"
          || nextRun.status === "regenerating_chapter"
        ) {
          await loadChapterReviewState(nextRun.run_id);
        }
        if (nextRun.status === "planned") {
          await loadPlanningArtifacts(nextRun.run_id);
          setGenerationRequested(false);
        }
        if (nextRun.status === "succeeded") {
          await loadFinalArtifacts(nextRun.run_id);
          setActiveArtifactPanel("yaml");
          setGenerationRequested(false);
        }
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : String(nextError));
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [run, isPolling]);

  useEffect(() => {
    const timers: number[] = [];
    for (const item of chapterReviews) {
      if (!item.card || typedSummaries[item.review.chapter_id] !== undefined) {
        continue;
      }
      const summary = item.card.summary;
      let cursor = 0;
      setTypedSummaries((current) => ({ ...current, [item.review.chapter_id]: "" }));
      const timer = window.setInterval(() => {
        cursor += 6;
        setTypedSummaries((current) => ({
          ...current,
          [item.review.chapter_id]: summary.slice(0, cursor),
        }));
        if (cursor >= summary.length) {
          window.clearInterval(timer);
        }
      }, 18);
      timers.push(timer);
    }
    return () => timers.forEach((timer) => window.clearInterval(timer));
  }, [chapterReviews, typedSummaries]);

  const artifactGroups = useMemo(() => {
    if (!run) {
      return [];
    }
    const workflowArtifacts = [
      "chapters.json",
      "chapter_cards.json",
      "reader_output.json",
      "story_bible.json",
      "story_bible.md",
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
      { title: "过程文件", items: workflowArtifacts },
      { title: "交付文件", items: deliverableArtifacts },
      { title: "其他文件", items: rest },
    ].filter((group) => group.items.length > 0);
  }, [run]);

  function clearRunState() {
    setRun(null);
    setPlanMarkdown("");
    setAdaptationPlan(null);
    setChapterCards([]);
    setChapterReviews([]);
    setReviewsExpanded(false);
    setReviewFilter("all");
    setOpenChapterId(null);
    setChatChapterId(null);
    setChatMessages([]);
    setAssistantDraft("");
    setVisibleThinking("");
    setToolEvents([]);
    setTypedSummaries({});
    setStoryBible(null);
    setStoryBibleMarkdown("");
    setYamlText("");
    setReportMarkdown("");
    setValidationReport(null);
    setActiveArtifactPanel(null);
    setGenerationRequested(false);
    setError(null);
  }

  async function refreshTasks() {
    try {
      const nextTasks = await listRuns();
      setTasks(nextTasks);
    } catch {
      setTasks([]);
    }
  }

  async function loadChapterReviewState(runId: string) {
    const response = await getChapterReviews(runId);
    setChapterReviews(response.items);
    setChapterCards(response.items.flatMap((item) => (item.card ? [item.card] : [])));
  }

  async function loadRunTask(runId: string) {
    setBusy(true);
    setError(null);
    setActiveArtifactPanel(null);
    setChatChapterId(null);
    setChatMessages([]);
    setAssistantDraft("");
    setVisibleThinking("");
    setToolEvents([]);
    try {
      const nextRun = await getRun(runId);
      setRun(nextRun);
      setPlanMarkdown("");
      setAdaptationPlan(null);
      setStoryBible(null);
      setStoryBibleMarkdown("");
      setYamlText("");
      setReportMarkdown("");
      setValidationReport(null);
      if (
        nextRun.artifacts.includes("chapter_reviews.json")
        || nextRun.artifacts.includes("chapter_cards.json")
      ) {
        await loadChapterReviewState(nextRun.run_id);
      } else {
        setChapterReviews([]);
        setChapterCards([]);
      }
      if (nextRun.artifacts.includes("adaptation_plan.json")) {
        await loadPlanningArtifacts(nextRun.run_id);
      }
      if (nextRun.artifacts.includes("script.yaml")) {
        await loadFinalArtifacts(nextRun.run_id);
      }
      await refreshTasks();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  function handleNewRun() {
    clearRunState();
    setFile(null);
  }

  function openArtifactPanel(panel: ArtifactPanel) {
    setChatChapterId(null);
    setActiveArtifactPanel(panel);
  }

  async function handleIntake() {
    setBusy(true);
    setError(null);
    setPlanMarkdown("");
    setAdaptationPlan(null);
    setChapterCards([]);
    setChapterReviews([]);
    setOpenChapterId(null);
    setChatChapterId(null);
    setChatMessages([]);
    setAssistantDraft("");
    setVisibleThinking("");
    setToolEvents([]);
    setTypedSummaries({});
    setStoryBible(null);
    setStoryBibleMarkdown("");
    setYamlText("");
    setReportMarkdown("");
    setValidationReport(null);
    setActiveArtifactPanel(null);
    setGenerationRequested(false);
    try {
      const nextRun = await intakeRun(inputText, file);
      setRun(nextRun);
      await refreshTasks();
      if (
        nextRun.status === "reading_chapters"
        || nextRun.status === "awaiting_chapter_review"
        || nextRun.artifacts.includes("chapter_reviews.json")
      ) {
        await loadChapterReviewState(nextRun.run_id);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleApproveChapter(chapterId: string) {
    if (!run) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await approveChapter(run.run_id, chapterId);
      setChapterReviews(response.items);
      await refreshTasks();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleApproveAllChapters() {
    if (!run) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await approveAllChapters(run.run_id);
      setChapterReviews(response.items);
      await refreshTasks();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleRegenerateChapter(chapterId: string) {
    if (!run) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setPlanMarkdown("");
      setAdaptationPlan(null);
      setStoryBible(null);
      setStoryBibleMarkdown("");
      setYamlText("");
      setReportMarkdown("");
      setValidationReport(null);
      setActiveArtifactPanel(null);
      const response = await regenerateChapter(run.run_id, chapterId);
      setChapterReviews(response.items);
      setRun({ ...run, status: "regenerating_chapter", current_stage: "regenerate_chapter" });
      await refreshTasks();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleBuildPlan() {
    if (!run) {
      return;
    }
    setBusy(true);
    setError(null);
    setActiveArtifactPanel(null);
    try {
      const nextRun = await buildPlan(run.run_id);
      setRun({ ...nextRun, status: "planning", current_stage: "build_story_bible" });
      await refreshTasks();
      if (nextRun.status === "planned" || nextRun.artifacts.includes("adaptation_plan.json")) {
        await loadPlanningArtifacts(nextRun.run_id);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenChapterChat(chapterId: string) {
    if (!run) {
      return;
    }
    setChatChapterId(chapterId);
    setActiveArtifactPanel(null);
    setAssistantDraft("");
    setVisibleThinking("");
    setToolEvents([]);
    try {
      const response = await getChapterChatMessages(run.run_id, chapterId);
      setChatMessages(response.messages.map((message) => ({
        role: message.role === "assistant" ? "assistant" : "user",
        content: message.content,
      })));
    } catch {
      setChatMessages([]);
    }
  }

  async function handleSendChapterChat() {
    if (!run || !chatChapterId || !chatInput.trim()) {
      return;
    }
    const message = chatInput.trim();
    setChatInput("");
    setChatMessages((current) => [...current, { role: "user", content: message }]);
    setBusy(true);
    setAssistantDraft("");
    setVisibleThinking("");
    setToolEvents([]);
    try {
      const response = await fetch(`${API_BASE_URL}/api/runs/${run.run_id}/chapter-cards/${chatChapterId}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      if (!response.ok || !response.body) {
        throw new Error(response.ok ? "Streaming response is empty." : await response.text());
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let collected = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const eventText of events) {
          const payload = parseSsePayload(eventText);
          if (!payload) {
            continue;
          }
          if (payload.type === "visible_thinking") {
            setVisibleThinking(String(payload.content ?? ""));
          }
          if (payload.type === "tool_event") {
            setToolEvents((current) => [
              ...current,
              `${String(payload.name ?? "tool")}：${String(payload.status ?? "ready")}`,
            ]);
          }
          if (payload.type === "assistant_delta") {
            const chunk = String(payload.content ?? "");
            collected += chunk;
            setAssistantDraft(collected);
          }
          if (payload.type === "final") {
            const content = collected || String(payload.content ?? "");
            setChatMessages((current) => [...current, { role: "assistant", content }]);
            setAssistantDraft("");
          }
          if (payload.type === "error") {
            throw new Error(String(payload.content ?? "Chapter chat failed."));
          }
        }
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
      setAssistantDraft("");
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
    setActiveArtifactPanel(null);
    setGenerationRequested(true);
    try {
      const nextRun = await generateRun(run.run_id, controls);
      setRun(nextRun);
      if (nextRun.status === "succeeded") {
        await loadFinalArtifacts(nextRun.run_id);
        setActiveArtifactPanel("yaml");
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
      setActiveArtifactPanel("report");
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

  async function loadPlanningArtifacts(runId: string) {
    const [nextPlanMarkdown, nextPlanJson, cardsText, bibleText, bibleMarkdown] = await Promise.all([
      getArtifactWithRetry(runId, "adaptation_plan.md"),
      getArtifactWithRetry(runId, "adaptation_plan.json"),
      getArtifactWithRetry(runId, "chapter_cards.json"),
      getArtifactWithRetry(runId, "story_bible.json"),
      getArtifactWithRetry(runId, "story_bible.md"),
    ]);
    setPlanMarkdown(nextPlanMarkdown);
    setAdaptationPlan(JSON.parse(nextPlanJson) as AdaptationPlan);
    setChapterCards(JSON.parse(cardsText) as ChapterCard[]);
    setStoryBible(JSON.parse(bibleText) as StoryBible);
    setStoryBibleMarkdown(bibleMarkdown);
  }

  async function loadFinalArtifacts(runId: string) {
    const [yaml, report] = await Promise.all([
      getArtifactWithRetry(runId, "script.yaml"),
      getArtifactWithRetry(runId, "adaptation_report.md"),
    ]);
    setYamlText(yaml);
    setReportMarkdown(report);
  }

  async function getArtifactWithRetry(runId: string, artifact: string): Promise<string> {
    let lastError: unknown;
    for (let attempt = 0; attempt < 4; attempt += 1) {
      try {
        return await getArtifact(runId, artifact);
      } catch (nextError) {
        lastError = nextError;
        await new Promise((resolve) => window.setTimeout(resolve, 350));
      }
    }
    throw lastError instanceof Error ? lastError : new Error(String(lastError));
  }

  function updateControl<K extends keyof AuthorControls>(key: K, value: AuthorControls[K]) {
    setControls((current) => ({ ...current, [key]: value }));
  }

  async function refreshLlmStatus() {
    try {
      const status = await getLlmStatus();
      setLlmStatus(status);
    } catch {
      setLlmStatus(null);
    }
  }

  async function handleTestLlm() {
    setBusy(true);
    setError(null);
    try {
      const result = await testLlmConnection();
      setLlmTestResult(result);
      setLlmStatus(result);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  function listFromText(value: string): string[] {
    return value
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  return (
    <div className={sidePanelOpen ? "workspace workspace-with-artifact" : "workspace workspace-compact"}>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <strong>Novel2Script</strong>
          <span>AI 改编副编剧</span>
        </div>
        <button className="new-run-button" type="button" onClick={handleNewRun}>
          新建改编
        </button>
        <div className="run-pill">{phaseLabel(phase)}</div>
        <button className="settings-button" type="button" onClick={() => setSettingsOpen(true)}>
          模型设置
        </button>
        <nav className="step-nav" aria-label="流程步骤">
          {stepLabels.map((label, index) => (
            <div className={index <= activeStepIndex(phase) ? "step-item active" : "step-item"} key={label}>
              <span>{index + 1}</span>
              {label}
            </div>
          ))}
        </nav>
        <TaskList activeRunId={run?.run_id ?? null} onSelect={loadRunTask} tasks={tasks} />
        <div className="sidebar-actions">
          <button type="button" disabled={!chapterCards.length} onClick={() => openArtifactPanel("chapterCards")}>
            章节理解卡
          </button>
          <button type="button" disabled={!storyBibleMarkdown} onClick={() => openArtifactPanel("storyBible")}>
            Story Bible
          </button>
          <button type="button" disabled={!yamlText} onClick={() => openArtifactPanel("yaml")}>
            打开 YAML
          </button>
          <button type="button" disabled={!reportMarkdown && !validationReport} onClick={() => openArtifactPanel("report")}>
            查看报告
          </button>
          <button type="button" disabled={!hasArtifacts} onClick={() => openArtifactPanel("downloads")}>
            下载产物
          </button>
          <button type="button" disabled={!run} onClick={() => openArtifactPanel("details")}>
            运行详情
          </button>
        </div>
        <a className="health-link" href={`${API_BASE_URL}/health`} target="_blank">
          API health
        </a>
      </aside>

      {settingsOpen ? (
        <SettingsDrawer
          busy={busy}
          llmStatus={llmStatus}
          llmTestResult={llmTestResult}
          onClose={() => setSettingsOpen(false)}
          onRefresh={refreshLlmStatus}
          onTest={handleTestLlm}
        />
      ) : null}

      <main className="chat-shell">
        <section className="chat-header">
          <p>AI Co-writer Workspace</p>
          <h1>把小说改成可表演、可追踪、可继续打磨的剧本初稿</h1>
        </section>

        <section className="message-list" aria-label="副编剧对话流">
          <AssistantMessage title="我会先读小说，再给你一份改编计划">
            <p>
              我不会一上来直接交 YAML。先把章节、人物、线索和改编风险梳理出来，
              等你确认剧本类型、改编尺度和保留内容后，再生成可编辑剧本。
            </p>
          </AssistantMessage>

          <UserMessage title="小说输入">
            <textarea
              className="novel-input"
              value={inputText}
              onChange={(event) => {
                setInputText(event.target.value);
                setFile(null);
              }}
              placeholder="粘贴至少三章小说文本..."
            />
            <div className="inline-actions">
              <label className="file-button">
                上传 .txt
                <input accept=".txt" type="file" onChange={handleFile} />
              </label>
              <button type="button" onClick={() => setInputText(sampleText)}>
                加载示例
              </button>
              <button type="button" disabled={busy || isPolling} onClick={handleIntake}>
                开始分析
              </button>
            </div>
            {file ? <p className="hint">已选择文件：{file.name}</p> : null}
          </UserMessage>

          {phase === "analyzing" || phase === "generating" ? (
            <AssistantMessage title={phase === "analyzing" ? "我正在阅读章节、识别人物和线索" : "我正在按确认的计划生成剧本"}>
              <StageSummary run={run} />
            </AssistantMessage>
          ) : null}

          {chapterReviews.length ? (
            <AssistantMessage title="章节理解确认">
              <ChapterReviewWorkbench
                allApproved={allChaptersApproved}
                busy={busy}
                canBuildPlan={canBuildPlan}
                expanded={reviewsExpanded}
                filter={reviewFilter}
                items={chapterReviews}
                onApprove={handleApproveChapter}
                onApproveAll={handleApproveAllChapters}
                onBuildPlan={handleBuildPlan}
                onDiscuss={handleOpenChapterChat}
                onFilterChange={setReviewFilter}
                onRegenerate={handleRegenerateChapter}
                onToggleExpanded={() => setReviewsExpanded((current) => !current)}
                openChapterId={openChapterId}
                setOpenChapterId={setOpenChapterId}
                typedSummaries={typedSummaries}
              />
            </AssistantMessage>
          ) : null}

          {planMarkdown ? (
            <AssistantMessage title="副编剧建议">
              <LongNovelOverview
                chapterCards={chapterCards}
                storyBible={storyBible}
                totalChapterChars={totalChapterChars}
              />
              <PlanCards fallbackPlan={fallbackPlan} plan={adaptationPlan} />
            </AssistantMessage>
          ) : null}

          {planMarkdown ? (
            <UserMessage title="确认改编方向">
              <AuthorControlCard
                controls={controls}
                updateControl={updateControl}
                listFromText={listFromText}
              />
              <div className="inline-actions">
                <button
                  type="button"
                  onClick={() => updateControl("adaptation_scale", "faithful")}
                >
                  更忠实原文
                </button>
                <button
                  type="button"
                  onClick={() => updateControl("style_focus", "suspense")}
                >
                  增强冲突
                </button>
                <button
                  type="button"
                  onClick={() => updateControl("adaptation_scale", "balanced")}
                >
                  减少 AI 新增
                </button>
                <button type="button" disabled={!canGenerate || busy || isPolling} onClick={handleGenerate}>
                  采纳计划并生成剧本
                </button>
              </div>
            </UserMessage>
          ) : null}

          {completed ? (
            <AssistantMessage title="剧本已生成">
              <p>我已经生成 YAML，并标记了来源、AI 新增内容、修改建议和生产提示。</p>
              <div className="inline-actions">
                <button type="button" onClick={() => openArtifactPanel("yaml")}>
                  打开 YAML
                </button>
                <button type="button" onClick={() => openArtifactPanel("report")}>
                  查看报告
                </button>
                <button type="button" onClick={() => openArtifactPanel("downloads")}>
                  下载产物
                </button>
              </div>
            </AssistantMessage>
          ) : null}

          {phase === "failed" || error ? (
            <AssistantMessage title="这次运行遇到问题">
              <p className="error-text">{error ?? run?.error}</p>
              <button type="button" onClick={handleIntake}>
                重新分析
              </button>
            </AssistantMessage>
          ) : null}
        </section>
      </main>

      {chatChapterId ? (
        <ChapterChatPanel
          assistantDraft={assistantDraft}
          busy={busy}
          chapterItem={activeChatChapter}
          input={chatInput}
          messages={chatMessages}
          onChangeInput={setChatInput}
          onClose={() => setChatChapterId(null)}
          onRegenerate={handleRegenerateChapter}
          onSend={handleSendChapterChat}
          toolEvents={toolEvents}
          visibleThinking={visibleThinking}
        />
      ) : activeArtifactPanel ? (
        <ArtifactPanelView
          activePanel={activeArtifactPanel}
          artifactGroups={artifactGroups}
          canValidate={canValidate}
          chapterCards={chapterCards}
          handleDownloadEditedYaml={handleDownloadEditedYaml}
          handleValidateYaml={handleValidateYaml}
          reportMarkdown={reportMarkdown}
          run={run}
          schema={schema}
          setActivePanel={setActiveArtifactPanel}
          setYamlText={setYamlText}
          storyBible={storyBible}
          storyBibleMarkdown={storyBibleMarkdown}
          validationReport={validationReport}
          yamlText={yamlText}
        />
      ) : null}
    </div>
  );
}

function TaskList({
  activeRunId,
  onSelect,
  tasks,
}: {
  activeRunId: string | null;
  onSelect: (runId: string) => void;
  tasks: RunListItem[];
}) {
  return (
    <section className="task-list" aria-label="任务列表">
      <div className="task-list-title">任务</div>
      {tasks.length ? (
        tasks.slice(0, 12).map((task) => (
          <button
            className={task.run_id === activeRunId ? "task-item active" : "task-item"}
            key={task.run_id}
            type="button"
            onClick={() => onSelect(task.run_id)}
          >
            <strong>{task.title || "未命名改编"}</strong>
            <span>{runStatusLabel(task.status)} · {formatTaskTime(task.updated_at)}</span>
          </button>
        ))
      ) : (
        <div className="empty-task">还没有任务</div>
      )}
    </section>
  );
}

function ChapterReviewWorkbench({
  allApproved,
  busy,
  canBuildPlan,
  expanded,
  filter,
  items,
  onApprove,
  onApproveAll,
  onBuildPlan,
  onDiscuss,
  onFilterChange,
  onRegenerate,
  onToggleExpanded,
  openChapterId,
  setOpenChapterId,
  typedSummaries,
}: {
  allApproved: boolean;
  busy: boolean;
  canBuildPlan: boolean;
  expanded: boolean;
  filter: ReviewFilter;
  items: ChapterReviewItem[];
  onApprove: (chapterId: string) => void;
  onApproveAll: () => void;
  onBuildPlan: () => void;
  onDiscuss: (chapterId: string) => void;
  onFilterChange: (filter: ReviewFilter) => void;
  onRegenerate: (chapterId: string) => void;
  onToggleExpanded: () => void;
  openChapterId: string | null;
  setOpenChapterId: (chapterId: string | null) => void;
  typedSummaries: Record<string, string>;
}) {
  const filtered = filterReviewItems(items, filter);
  const visibleItems = expanded ? filtered : filtered.slice(0, 5);
  const readyCount = items.filter((item) => item.review.status === "ready" || item.review.status === "approved").length;
  const approvedCount = items.filter((item) => item.review.status === "approved").length;
  return (
    <div className="review-workbench">
      <div className="review-toolbar">
        <div>
          <span>已读懂 {readyCount}/{items.length} 章</span>
          <strong>已通过 {approvedCount}/{items.length} 章</strong>
        </div>
        <div className="segmented-control" role="group" aria-label="章节筛选">
          <button className={filter === "all" ? "active" : ""} type="button" onClick={() => onFilterChange("all")}>
            全部
          </button>
          <button className={filter === "pending" ? "active" : ""} type="button" onClick={() => onFilterChange("pending")}>
            未通过
          </button>
          <button className={filter === "attention" ? "active" : ""} type="button" onClick={() => onFilterChange("attention")}>
            需重读
          </button>
        </div>
      </div>
      <div className="review-actions">
        <button type="button" disabled={!items.length || busy} onClick={onApproveAll}>
          全部通过
        </button>
        <button type="button" disabled={!canBuildPlan || busy} onClick={onBuildPlan}>
          生成 Story Bible 和改编计划
        </button>
        <button type="button" disabled={filtered.length <= 5} onClick={onToggleExpanded}>
          {expanded ? "收起章节" : "展开全部"}
        </button>
      </div>
      <div className="review-grid" data-testid="chapter-review-grid">
        {visibleItems.map((item) => (
          <ChapterReviewCard
            item={item}
            key={item.review.chapter_id}
            onApprove={onApprove}
            onDiscuss={onDiscuss}
            onRegenerate={onRegenerate}
            open={openChapterId === item.review.chapter_id}
            setOpen={(nextOpen) => setOpenChapterId(nextOpen ? item.review.chapter_id : null)}
            typedSummary={typedSummaries[item.review.chapter_id]}
          />
        ))}
      </div>
      {!allApproved ? (
        <p className="review-hint">Story Bible 和改编计划只会基于已通过的章节理解卡生成。</p>
      ) : (
        <p className="review-hint success-text">所有章节已通过，可以进入改编计划。</p>
      )}
    </div>
  );
}

function ChapterReviewCard({
  item,
  onApprove,
  onDiscuss,
  onRegenerate,
  open,
  setOpen,
  typedSummary,
}: {
  item: ChapterReviewItem;
  onApprove: (chapterId: string) => void;
  onDiscuss: (chapterId: string) => void;
  onRegenerate: (chapterId: string) => void;
  open: boolean;
  setOpen: (open: boolean) => void;
  typedSummary?: string;
}) {
  const card = item.card;
  const chapterId = item.review.chapter_id;
  return (
    <article className={`review-card ${reviewStatusClass(item.review.status)}`}>
      <div className="review-card-head">
        <div>
          <strong>
            第 {item.chapter.index} 章 · {item.chapter.title}
          </strong>
          <span>{item.chapter.char_count} 字 · {reviewStatusLabel(item.review.status)}</span>
        </div>
        <span className="revision-pill">重读 {item.review.revision_count}</span>
      </div>
      {card ? (
        <>
          <p className="review-summary">{typedSummary ?? card.summary}</p>
          <div className="review-tags">
            {card.characters.slice(0, 4).map((character) => <span key={character}>{character}</span>)}
          </div>
          {open ? (
            <div className="review-details">
              <DetailList title="关键事件" items={card.key_events} />
              <DetailList title="线索" items={card.clues} />
              <DetailList title="改编机会" items={card.adaptation_opportunities} />
              <DetailList title="连续性提示" items={card.continuity_notes} />
            </div>
          ) : null}
        </>
      ) : (
        <p className="review-summary">这一章还在读取中，理解卡生成后会自动出现。</p>
      )}
      {item.review.error ? <p className="error-text">{item.review.error}</p> : null}
      <div className="review-card-actions">
        <button type="button" disabled={!card} onClick={() => setOpen(!open)}>
          {open ? "收起详情" : "查看详情"}
        </button>
        <button type="button" disabled={!card} onClick={() => onDiscuss(chapterId)}>
          讨论/修改理解
        </button>
        <button type="button" disabled={!card || item.review.status === "approved"} onClick={() => onApprove(chapterId)}>
          通过
        </button>
        <button type="button" onClick={() => onRegenerate(chapterId)}>
          重新理解
        </button>
      </div>
    </article>
  );
}

function ChapterChatPanel({
  assistantDraft,
  busy,
  chapterItem,
  input,
  messages,
  onChangeInput,
  onClose,
  onRegenerate,
  onSend,
  toolEvents,
  visibleThinking,
}: {
  assistantDraft: string;
  busy: boolean;
  chapterItem: ChapterReviewItem | null;
  input: string;
  messages: Array<{ role: "user" | "assistant"; content: string }>;
  onChangeInput: (value: string) => void;
  onClose: () => void;
  onRegenerate: (chapterId: string) => void;
  onSend: () => void;
  toolEvents: string[];
  visibleThinking: string;
}) {
  return (
    <aside className="chapter-chat-panel" data-testid="chapter-chat-panel">
      <div className="artifact-header">
        <div>
          <span>章节讨论</span>
          <strong>{chapterItem?.chapter.title ?? "章节"}</strong>
        </div>
        <button type="button" onClick={onClose}>
          关闭
        </button>
      </div>
      <div className="chapter-chat-context">
        {chapterItem?.card ? (
          <>
            <span>{chapterItem.review.chapter_id} · {chapterItem.chapter.char_count} 字</span>
            <p>{chapterItem.card.summary}</p>
            <button type="button" onClick={() => onRegenerate(chapterItem.review.chapter_id)}>
              重新理解本章
            </button>
          </>
        ) : (
          <p>等待章节理解卡生成。</p>
        )}
      </div>
      <div className="chapter-chat-messages" aria-label="章节聊天消息">
        {messages.length ? messages.map((message, index) => (
          <div className={`chapter-chat-message ${message.role}`} key={`${message.role}-${index}`}>
            <span>{message.role === "assistant" ? "AI" : "你"}</span>
            <p>{message.content}</p>
          </div>
        )) : (
          <div className="hint-card">你可以告诉 AI：哪条线索没读准、哪个人物动机必须保留、哪些心理描写不要乱改。</div>
        )}
        {visibleThinking ? (
          <div className="visible-thinking">
            <span>思考摘要</span>
            <p>{visibleThinking}</p>
          </div>
        ) : null}
        {toolEvents.length ? (
          <div className="tool-events">
            {toolEvents.map((event, index) => <span key={`${event}-${index}`}>{event}</span>)}
          </div>
        ) : null}
        {assistantDraft ? (
          <div className="chapter-chat-message assistant streaming">
            <span>AI</span>
            <p>{assistantDraft}</p>
          </div>
        ) : null}
      </div>
      <div className="chapter-chat-input">
        <textarea
          value={input}
          onChange={(event) => onChangeInput(event.target.value)}
          placeholder="指出你不满意的地方，例如：第二章周砚的动机读偏了..."
        />
        <button type="button" disabled={busy || !input.trim()} onClick={onSend}>
          发送
        </button>
      </div>
    </aside>
  );
}

function DetailList({ items, title }: { items: string[]; title: string }) {
  return (
    <div className="detail-list">
      <span>{title}</span>
      <ul>
        {items.length ? items.map((item) => <li key={item}>{item}</li>) : <li>暂无</li>}
      </ul>
    </div>
  );
}

function AssistantMessage({ children, title }: { children: ReactNode; title: string }) {
  return (
    <article className="message assistant-message">
      <div className="avatar">AI</div>
      <div className="message-card">
        <h2>{title}</h2>
        {children}
      </div>
    </article>
  );
}

function UserMessage({ children, title }: { children: ReactNode; title: string }) {
  return (
    <article className="message user-message">
      <div className="avatar">你</div>
      <div className="message-card">
        <h2>{title}</h2>
        {children}
      </div>
    </article>
  );
}

function SettingsDrawer({
  busy,
  llmStatus,
  llmTestResult,
  onClose,
  onRefresh,
  onTest,
}: {
  busy: boolean;
  llmStatus: LlmStatus | null;
  llmTestResult: LlmTestResult | null;
  onClose: () => void;
  onRefresh: () => void;
  onTest: () => void;
}) {
  return (
    <div className="settings-backdrop" role="presentation">
      <aside className="settings-drawer" aria-label="模型设置">
        <div className="artifact-header">
          <div>
            <span>Settings</span>
            <strong>模型设置</strong>
          </div>
          <button type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="settings-body">
          <div className="notice">
            API Key 请填入 <strong>backend/.env</strong>，不要粘贴到页面或提交到仓库。
          </div>
          <div className="run-detail">
            <span>模式</span>
            <strong>{llmStatus?.mode === "real" ? "Real Model" : "Mock Demo"}</strong>
            <span>模型</span>
            <strong>{llmStatus?.model ?? "未连接"}</strong>
            <span>API Key</span>
            <strong>{llmStatus?.api_key_configured ? "已配置" : "未配置"}</strong>
            <span>Base URL</span>
            <strong>{llmStatus?.base_url_configured ? "已配置" : "默认 OpenAI"}</strong>
          </div>
          <div className="inline-actions">
            <button type="button" disabled={busy} onClick={onRefresh}>
              刷新状态
            </button>
            <button type="button" disabled={busy} onClick={onTest}>
              测试连接
            </button>
          </div>
          {llmTestResult ? (
            <div className={llmTestResult.success ? "notice success-notice" : "notice warning-notice"}>
              <strong>{llmTestResult.success ? "连接可用" : "连接不可用"}</strong>
              <div>{llmTestResult.message}</div>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function LongNovelOverview({
  chapterCards,
  storyBible,
  totalChapterChars,
}: {
  chapterCards: ChapterCard[];
  storyBible: StoryBible | null;
  totalChapterChars: number;
}) {
  if (!chapterCards.length || !storyBible) {
    return <div className="hint-card">章节理解卡和 Story Bible 生成后，会在这里展示长篇承载结果。</div>;
  }
  return (
    <div className="long-novel-overview">
      <div className="metric-row">
        <div>
          <span>章节</span>
          <strong>{chapterCards.length}</strong>
        </div>
        <div>
          <span>总字数</span>
          <strong>{totalChapterChars}</strong>
        </div>
        <div>
          <span>建议先生成</span>
          <strong>第 {storyBible.recommended_generation_scope.join(", ")} 章</strong>
        </div>
      </div>
      <div className="insight-card wide">
        <span>全书主线</span>
        <p>{storyBible.main_plot}</p>
      </div>
      <div className="chapter-card-list">
        {chapterCards.slice(0, 5).map((card) => (
          <div className="chapter-card-item" key={card.chapter_id}>
            <strong>
              {card.title} · {card.char_count} 字
            </strong>
            <p>{card.summary}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function AuthorControlCard({
  controls,
  listFromText,
  updateControl,
}: {
  controls: AuthorControls;
  listFromText: (value: string) => string[];
  updateControl: <K extends keyof AuthorControls>(key: K, value: AuthorControls[K]) => void;
}) {
  return (
    <div className="control-card">
      <label>
        剧本类型
        <select
          value={controls.format_type}
          onChange={(event) => updateControl("format_type", event.target.value as AuthorControls["format_type"])}
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
          onChange={(event) => updateControl("adaptation_scale", event.target.value as AuthorControls["adaptation_scale"])}
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
          onChange={(event) => updateControl("style_focus", event.target.value as AuthorControls["style_focus"])}
        >
          {focusOptions.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        必须保留
        <textarea
          value={controls.preserve_items.join("\n")}
          onChange={(event) => updateControl("preserve_items", listFromText(event.target.value))}
        />
      </label>
      <label>
        禁止改动
        <textarea
          value={controls.forbidden_changes.join("\n")}
          onChange={(event) => updateControl("forbidden_changes", listFromText(event.target.value))}
        />
      </label>
      <label>
        作者备注
        <textarea
          value={controls.author_notes ?? ""}
          onChange={(event) => updateControl("author_notes", event.target.value)}
        />
      </label>
    </div>
  );
}

function PlanCards({
  fallbackPlan,
  plan,
}: {
  fallbackPlan: ParsedPlan;
  plan: AdaptationPlan | null;
}) {
  const recommended = plan
    ? [
        labelFromOptions(formatOptions, plan.recommended_format_type),
        labelFromOptions(focusOptions, plan.recommended_style_focus),
        labelFromOptions(scaleOptions, plan.recommended_adaptation_scale),
      ].join(" / ")
    : fallbackPlan.recommended || "短剧 / 心理外化 / 平衡改编";
  const rationale = plan?.format_rationale.length
    ? plan.format_rationale
    : plan?.rationale.length
      ? plan.rationale
      : fallbackPlan.rationale;
  const risks = plan?.risks.length
    ? plan.risks.map((risk) => `${risk.target}：${risk.message}`)
    : fallbackPlan.risks;
  const technicalNotes = plan?.technical_notes ?? [];

  return (
    <div className="plan-card-grid">
      <div className="insight-card wide">
        <span>我理解的故事</span>
        <p>{plan?.summary || fallbackPlan.summary || "已完成章节检测，准备根据原文线索制定改编方向。"}</p>
      </div>
      <div className="insight-card">
        <span>推荐改编方向</span>
        <p>{recommended}</p>
      </div>
      <div className="insight-card">
        <span>为什么推荐这个方向</span>
        <ul>
          {rationale.length ? rationale.map((item) => <li key={item}>{item}</li>) : <li>先保留主线，再把心理描写转成动作和对白。</li>}
        </ul>
      </div>
      <div className="insight-card wide">
        <span>分章改编理由</span>
        {plan?.scene_plan.length ? (
          <div className="scene-reason-list">
            {plan.scene_plan.slice(0, 5).map((scene) => (
              <div className="scene-reason-card" key={scene.id}>
                <strong>
                  {scene.id} · {scene.title} · 第 {scene.source_chapters.join(", ")} 章
                </strong>
                <dl>
                  <div>
                    <dt>原文功能</dt>
                    <dd>{scene.source_function || scene.dramatic_purpose}</dd>
                  </div>
                  <div>
                    <dt>改编处理</dt>
                    <dd>{scene.adaptation_treatment || scene.dramatic_purpose}</dd>
                  </div>
                  <div>
                    <dt>为什么这样改</dt>
                    <dd>{scene.adaptation_reason || "把章节里的叙述内容转成可表演动作、对白和冲突。"}</dd>
                  </div>
                  {scene.performance_notes ? (
                    <div>
                      <dt>表演化提示</dt>
                      <dd>{scene.performance_notes}</dd>
                    </div>
                  ) : null}
                  {scene.risk_note ? (
                    <div>
                      <dt>风险提醒</dt>
                      <dd>{scene.risk_note}</dd>
                    </div>
                  ) : null}
                </dl>
              </div>
            ))}
          </div>
        ) : (
          <ul>
            {fallbackPlan.scenes.length ? fallbackPlan.scenes.map((item) => <li key={item}>{item}</li>) : <li>AI 会按章节拆成可表演的场景。</li>}
          </ul>
        )}
      </div>
      {technicalNotes.length ? (
        <div className="insight-card wide technical-notes">
          <span>长文本处理说明</span>
          <ul>
            {technicalNotes.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      ) : null}
      <div className="insight-card wide">
        <span>风险提醒</span>
        <ul>
          {risks.length ? risks.map((item) => <li key={item}>{item}</li>) : <li>心理描写需要外化，避免剧本只是在解释背景。</li>}
        </ul>
      </div>
    </div>
  );
}

function ArtifactPanelView({
  activePanel,
  artifactGroups,
  canValidate,
  chapterCards,
  handleDownloadEditedYaml,
  handleValidateYaml,
  reportMarkdown,
  run,
  schema,
  setActivePanel,
  setYamlText,
  storyBible,
  storyBibleMarkdown,
  validationReport,
  yamlText,
}: {
  activePanel: ArtifactPanel;
  artifactGroups: { title: string; items: string[] }[];
  canValidate: boolean;
  chapterCards: ChapterCard[];
  handleDownloadEditedYaml: () => void;
  handleValidateYaml: () => void;
  reportMarkdown: string;
  run: RunInfo | null;
  schema: Record<string, unknown> | null;
  setActivePanel: (panel: ArtifactPanel | null) => void;
  setYamlText: (value: string) => void;
  storyBible: StoryBible | null;
  storyBibleMarkdown: string;
  validationReport: ValidationReport | null;
  yamlText: string;
}) {
  return (
    <aside className="artifact-panel" data-testid="artifact-panel">
      <div className="artifact-header">
        <div>
          <span>产物</span>
          <strong>{panelTitle(activePanel)}</strong>
        </div>
        <button type="button" aria-label="关闭产物面板" onClick={() => setActivePanel(null)}>
          关闭
        </button>
      </div>
      <div className="artifact-tabs">
        {(["chapterCards", "storyBible", "yaml", "report", "downloads", "details"] as ArtifactPanel[]).map((panel) => (
          <button
            className={activePanel === panel ? "active" : ""}
            disabled={
              (panel === "chapterCards" && !chapterCards.length)
              || (panel === "storyBible" && !storyBible)
              || (panel === "yaml" && !yamlText)
            }
            key={panel}
            type="button"
            onClick={() => setActivePanel(panel)}
          >
            {panelTitle(panel)}
          </button>
        ))}
      </div>
      {activePanel === "chapterCards" ? (
        <div className="artifact-body">
          {chapterCards.length ? (
            <div className="chapter-card-list">
              {chapterCards.map((card) => (
                <div className="chapter-card-item" key={card.chapter_id}>
                  <strong>
                    {card.chapter_id} · {card.title} · {card.char_count} 字
                  </strong>
                  <p>{card.summary}</p>
                  <small>线索：{card.clues.join(" / ") || "暂无"}</small>
                </div>
              ))}
            </div>
          ) : (
            <div className="hint-card">分析完成后，这里会显示每章理解卡。</div>
          )}
        </div>
      ) : null}
      {activePanel === "storyBible" ? (
        <div className="artifact-body">
          {storyBible ? (
            <>
              <div className="notice">
                <strong>主线</strong>
                <div>{storyBible.main_plot}</div>
              </div>
              <div className="report">{storyBibleMarkdown}</div>
            </>
          ) : (
            <div className="hint-card">分析完成后，这里会显示 Story Bible。</div>
          )}
        </div>
      ) : null}
      {activePanel === "yaml" ? (
        <div className="artifact-body">
          {yamlText ? (
            <>
              <YamlEditor value={yamlText} schema={schema} onChange={setYamlText} />
              <div className="inline-actions">
                <button type="button" disabled={!canValidate} onClick={handleValidateYaml}>
                  重新校验 YAML
                </button>
                <button type="button" disabled={!yamlText.trim()} onClick={handleDownloadEditedYaml}>
                  下载当前 YAML
                </button>
              </div>
            </>
          ) : (
            <div className="hint-card">生成完成后，这里会显示 YAML。</div>
          )}
        </div>
      ) : null}
      {activePanel === "report" ? (
        <div className="artifact-body">
          <ReportPanel report={validationReport} markdown={reportMarkdown} />
        </div>
      ) : null}
      {activePanel === "downloads" ? (
        <div className="artifact-body">
          {artifactGroups.length ? (
            <div className="download-grid">
              {artifactGroups.map((group) => (
                <div className="download-group" key={group.title}>
                  <h3>{group.title}</h3>
                  {group.items.map((artifact) => (
                    <a key={artifact} href={run ? artifactUrl(run.run_id, artifact) : "#"} target="_blank">
                      下载 {artifact}
                    </a>
                  ))}
                </div>
              ))}
            </div>
          ) : (
            <div className="hint-card">还没有可下载产物。</div>
          )}
        </div>
      ) : null}
      {activePanel === "details" ? (
        <div className="artifact-body">
          {run ? (
            <>
              <div className="run-detail">
                <span>run_id</span>
                <strong>{run.run_id}</strong>
                <span>状态</span>
                <strong>{run.status}</strong>
                {run.error ? <p className="error-text">{run.error}</p> : null}
              </div>
              <StageSummary run={run} />
            </>
          ) : (
            <div className="hint-card">创建 run 后，这里会显示运行详情。</div>
          )}
        </div>
      ) : null}
    </aside>
  );
}

function StageSummary({ run }: { run: RunInfo | null }) {
  if (!run) {
    return <div className="hint-card">等待开始。</div>;
  }
  return (
    <div className="stage-list">
      {run.stages.map((stage) => (
        <div className="stage-row" key={stage.name}>
          <strong>{stage.name}</strong>
          <span className={`status-dot ${stage.status}`}>{stage.status}</span>
          {stage.message ? <small>{stage.message}</small> : null}
        </div>
      ))}
    </div>
  );
}

type ParsedPlan = {
  recommended: string;
  rationale: string[];
  risks: string[];
  scenes: string[];
  summary: string;
};

function parsePlanMarkdown(markdown: string): ParsedPlan {
  const lines = markdown.split(/\r?\n/).map((line) => line.trim());
  return {
    recommended: [
      findValue(lines, "- 推荐剧本类型:") || findValue(lines, "- Recommended format:"),
      findValue(lines, "- 推荐风格:") || findValue(lines, "- Recommended style:"),
      findValue(lines, "- 推荐尺度:") || findValue(lines, "- Recommended scale:"),
    ]
      .filter(Boolean)
      .join(" / "),
    rationale: sectionBullets(lines, "## 为什么推荐这个方向").length
      ? sectionBullets(lines, "## 为什么推荐这个方向")
      : sectionBullets(lines, "## Rationale"),
    risks: (
      sectionBullets(lines, "## 风险提醒").length
        ? sectionBullets(lines, "## 风险提醒")
        : sectionBullets(lines, "## Risks")
    ).map((item) => item.replace(/\*\*/g, "")),
    scenes: (
      sectionBullets(lines, "## 分章改编理由").length
        ? sectionBullets(lines, "## 分章改编理由")
        : sectionBullets(lines, "## Scene Plan")
    ).slice(0, 5),
    summary: sectionText(lines, "## 我理解的故事") || sectionText(lines, "## Summary"),
  };
}

function findValue(lines: string[], prefix: string): string {
  const line = lines.find((item) => item.startsWith(prefix));
  return line?.replace(prefix, "").replace(/`/g, "").trim() ?? "";
}

function sectionText(lines: string[], heading: string): string {
  const start = lines.indexOf(heading);
  if (start < 0) {
    return "";
  }
  const collected: string[] = [];
  for (const line of lines.slice(start + 1)) {
    if (line.startsWith("## ")) {
      break;
    }
    if (line) {
      collected.push(line);
    }
  }
  return collected.join(" ");
}

function sectionBullets(lines: string[], heading: string): string[] {
  const start = lines.indexOf(heading);
  if (start < 0) {
    return [];
  }
  const collected: string[] = [];
  for (const line of lines.slice(start + 1)) {
    if (line.startsWith("## ")) {
      break;
    }
    if (line.startsWith("- ")) {
      collected.push(line.slice(2));
    }
  }
  return collected;
}

function labelFromOptions<T extends string>(
  options: readonly (readonly [T, string])[],
  value: T,
): string {
  return options.find(([candidate]) => candidate === value)?.[1] ?? value;
}

function getConversationPhase(
  run: RunInfo | null,
  isPolling: boolean,
  generationRequested: boolean,
  error: string | null,
  yamlText: string,
): ConversationPhase {
  if (error || run?.status.startsWith("failed")) {
    return "failed";
  }
  if (!run) {
    return "idle";
  }
  if (yamlText && run.status === "succeeded") {
    return "completed";
  }
  if (run.status === "awaiting_chapter_review" || run.status === "regenerating_chapter") {
    return "reviewing";
  }
  if (run.status === "reading_chapters") {
    return "analyzing";
  }
  if (run.status === "planning") {
    return "analyzing";
  }
  if (generationRequested || (isPolling && run.status !== "planned")) {
    return "generating";
  }
  if (run.status === "planned") {
    return "planned";
  }
  return "analyzing";
}

function phaseLabel(phase: ConversationPhase): string {
  const labels: Record<ConversationPhase, string> = {
    idle: "未开始",
    analyzing: "分析中",
    reviewing: "等待章节确认",
    planned: "等待确认",
    generating: "生成中",
    completed: "已完成",
    failed: "需要处理",
  };
  return labels[phase];
}

function activeStepIndex(phase: ConversationPhase): number {
  const indexes: Record<ConversationPhase, number> = {
    idle: 0,
    analyzing: 1,
    reviewing: 1,
    planned: 2,
    generating: 3,
    completed: 4,
    failed: 0,
  };
  return indexes[phase];
}

function panelTitle(panel: ArtifactPanel): string {
  const labels: Record<ArtifactPanel, string> = {
    chapterCards: "章节理解卡",
    storyBible: "Story Bible",
    yaml: "YAML",
    report: "改编报告",
    downloads: "下载产物",
    details: "运行详情",
  };
  return labels[panel];
}

function filterReviewItems(items: ChapterReviewItem[], filter: ReviewFilter): ChapterReviewItem[] {
  if (filter === "pending") {
    return items.filter((item) => item.review.status !== "approved");
  }
  if (filter === "attention") {
    return items.filter((item) => item.review.status === "failed" || item.review.revision_count > 0);
  }
  return items;
}

function reviewStatusLabel(status: ChapterReviewItem["review"]["status"]): string {
  const labels: Record<ChapterReviewItem["review"]["status"], string> = {
    pending: "排队中",
    reading: "读取中",
    ready: "待确认",
    approved: "已通过",
    regenerating: "重读中",
    failed: "需处理",
  };
  return labels[status];
}

function reviewStatusClass(status: ChapterReviewItem["review"]["status"]): string {
  if (status === "approved") {
    return "approved";
  }
  if (status === "failed") {
    return "failed";
  }
  if (status === "reading" || status === "regenerating") {
    return "running";
  }
  return "ready";
}

function runStatusLabel(status: RunInfo["status"]): string {
  const labels: Partial<Record<RunInfo["status"], string>> = {
    queued: "排队中",
    running: "运行中",
    reading_chapters: "读章节",
    awaiting_chapter_review: "待确认",
    regenerating_chapter: "重读中",
    planning: "做计划",
    planned: "待生成",
    generating: "生成中",
    validating: "校验中",
    repairing: "修复中",
    exporting: "导出中",
    succeeded: "完成",
    failed_validation: "校验失败",
    failed_llm: "模型失败",
    failed_internal: "系统失败",
  };
  return labels[status] ?? status;
}

function formatTaskTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "刚刚";
  }
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function parseSsePayload(eventText: string): Record<string, unknown> | null {
  const dataLine = eventText
    .split(/\r?\n/)
    .find((line) => line.startsWith("data: "));
  if (!dataLine) {
    return null;
  }
  try {
    return JSON.parse(dataLine.slice(6));
  } catch {
    return null;
  }
}
