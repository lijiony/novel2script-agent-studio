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
  ChapterScriptReviewItem,
  FinalFeedbackResponse,
  LlmStatus,
  LlmTestResult,
  RunListItem,
  RunInfo,
  ValidationReport,
  applyFinalFeedback,
  approveAllChapters,
  approveAllChapterScripts,
  approveChapter,
  approveChapterScript,
  artifactUrl,
  buildPlan,
  confirmFinalScript,
  continuityMerge,
  generateRun,
  getArtifact,
  getChapterChatMessages,
  getChapterReviews,
  getChapterScriptChatMessages,
  getChapterScriptReviews,
  getLlmStatus,
  getRun,
  getScriptSchema,
  intakeRun,
  listRuns,
  regenerateChapter,
  regenerateChapterScript,
  testLlmConnection,
  validateYaml,
} from "@/lib/api";

type ArtifactPanel = "chapterCards" | "chapterScripts" | "storyBible" | "yaml" | "report" | "downloads" | "details";
type ConversationPhase = "idle" | "analyzing" | "reviewing" | "planned" | "generating" | "completed" | "failed";
type ReviewFilter = "all" | "pending" | "attention";
type ChatMode = "chapter" | "script";

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

const terminalStatuses = new Set(["succeeded", "awaiting_final_review", "failed_validation", "failed_llm", "failed_internal"]);

const defaultControls: AuthorControls = {
  format_type: "short_drama",
  adaptation_scale: "balanced",
  style_focus: "psychological",
  generation_scope: [],
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
  "剧本卡确认",
  "连贯性合成",
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
  const [chapterScriptReviews, setChapterScriptReviews] = useState<ChapterScriptReviewItem[]>([]);
  const [reviewsExpanded, setReviewsExpanded] = useState(false);
  const [scriptReviewsExpanded, setScriptReviewsExpanded] = useState(false);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("all");
  const [scriptReviewFilter, setScriptReviewFilter] = useState<ReviewFilter>("all");
  const [openChapterId, setOpenChapterId] = useState<string | null>(null);
  const [openScriptChapterId, setOpenScriptChapterId] = useState<string | null>(null);
  const [chatChapterId, setChatChapterId] = useState<string | null>(null);
  const [chatMode, setChatMode] = useState<ChatMode>("chapter");
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
  const [finalFeedbackOpen, setFinalFeedbackOpen] = useState(false);
  const [finalFeedbackCategory, setFinalFeedbackCategory] = useState<"continuity" | "script_point" | "chapter_and_continuity">("continuity");
  const [finalFeedbackText, setFinalFeedbackText] = useState("");
  const [finalFeedbackDesired, setFinalFeedbackDesired] = useState("");
  const [finalFeedbackResult, setFinalFeedbackResult] = useState<FinalFeedbackResponse | null>(null);
  const [finalFeedbackChapterId, setFinalFeedbackChapterId] = useState<string | null>(null);
  const [finalFeedbackApplying, setFinalFeedbackApplying] = useState(false);
  const [finalFeedbackMessages, setFinalFeedbackMessages] = useState<Array<{ role: "user" | "assistant"; content: string }>>([]);
  const [finalFeedbackDraft, setFinalFeedbackDraft] = useState("");
  const [finalFeedbackThinking, setFinalFeedbackThinking] = useState("");
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
  const allScriptsApproved = chapterScriptReviews.length > 0
    && chapterScriptReviews.every((item) => item.review.status === "approved" && item.script_card);
  const canReviewChapters = Boolean(run?.run_id && run.status === "awaiting_chapter_review");
  const canReviewScripts = Boolean(run?.run_id && run.status === "awaiting_script_review");
  const canBuildPlan = Boolean(run?.run_id && run.status === "awaiting_chapter_review" && allChaptersApproved);
  const canGenerate = Boolean(run?.run_id && run.status === "planned" && controls.generation_scope.length);
  const canContinuityMerge = Boolean(run?.run_id && run.status === "awaiting_script_review" && allScriptsApproved);
  const canValidate = Boolean(run?.run_id && yamlText.trim());
  const isPolling = Boolean(
    run
      && (
        (!terminalStatuses.has(run.status) && !["awaiting_chapter_review", "planned", "awaiting_script_review"].includes(run.status))
        || generationRequested
      ),
  );
  const phase = getConversationPhase(run, isPolling, generationRequested, error, yamlText);
  const fallbackPlan = useMemo(() => parsePlanMarkdown(planMarkdown), [planMarkdown]);
  const completed = phase === "completed";
  const totalChapterChars = chapterCards.reduce((sum, card) => sum + card.char_count, 0);
  const inputChapterEstimate = useMemo(() => estimateChapterCount(inputText), [inputText]);
  const approvedChapterCount = chapterReviews.filter((item) => item.review.status === "approved").length;
  const approvedScriptCount = chapterScriptReviews.filter((item) => item.review.status === "approved").length;
  const totalScriptScenes = chapterScriptReviews.reduce((sum, item) => sum + (item.script_card?.scenes.length ?? 0), 0);
  const activeChatChapter = chapterReviews.find((item) => item.review.chapter_id === chatChapterId) ?? null;
  const activeScriptChatChapter = chapterScriptReviews.find((item) => item.review.chapter_id === chatChapterId) ?? null;
  const artifactPanelOpen = Boolean(activeArtifactPanel);

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
        if (
          nextRun.status === "generating_chapter_scripts"
          || nextRun.status === "awaiting_script_review"
          || nextRun.status === "regenerating_chapter_script"
        ) {
          await loadChapterScriptReviewState(nextRun.run_id);
        }
        if (nextRun.status === "planned") {
          await loadPlanningArtifacts(nextRun.run_id);
          setGenerationRequested(false);
        }
        if (nextRun.status === "awaiting_script_review") {
          setGenerationRequested(false);
          setFinalFeedbackApplying(false);
        }
        if (nextRun.status === "succeeded" || nextRun.status === "awaiting_final_review") {
          await loadFinalArtifacts(nextRun.run_id);
          setActiveArtifactPanel("yaml");
          setGenerationRequested(false);
          setFinalFeedbackApplying(false);
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
      "chapter_script_cards.json",
      "chapter_script_reviews.json",
      "chapter_script_feedback.json",
      "chapter_script_chat_messages.json",
      "final_feedback_chat_messages.json",
      "continuity_report.md",
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
    setChapterScriptReviews([]);
    setReviewsExpanded(false);
    setScriptReviewsExpanded(false);
    setReviewFilter("all");
    setScriptReviewFilter("all");
    setOpenChapterId(null);
    setOpenScriptChapterId(null);
    setChatChapterId(null);
    setChatMode("chapter");
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
    setFinalFeedbackOpen(false);
    setFinalFeedbackText("");
    setFinalFeedbackDesired("");
    setFinalFeedbackResult(null);
    setFinalFeedbackChapterId(null);
    setFinalFeedbackApplying(false);
    setFinalFeedbackMessages([]);
    setFinalFeedbackDraft("");
    setFinalFeedbackThinking("");
    setActiveArtifactPanel(null);
    setGenerationRequested(false);
    setError(null);
    setControls((current) => ({ ...current, generation_scope: [] }));
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

  async function loadChapterScriptReviewState(runId: string) {
    const response = await getChapterScriptReviews(runId);
    setChapterScriptReviews(response.items);
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
      setControls((current) => ({ ...current, generation_scope: [] }));
      setPlanMarkdown("");
      setAdaptationPlan(null);
      setStoryBible(null);
      setStoryBibleMarkdown("");
      setYamlText("");
      setReportMarkdown("");
      setValidationReport(null);
      setChapterScriptReviews([]);
      setFinalFeedbackOpen(false);
      setFinalFeedbackText("");
      setFinalFeedbackDesired("");
      setFinalFeedbackResult(null);
      setFinalFeedbackChapterId(null);
      setFinalFeedbackApplying(false);
      setFinalFeedbackMessages([]);
      setFinalFeedbackDraft("");
      setFinalFeedbackThinking("");
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
      if (
        nextRun.artifacts.includes("chapter_script_reviews.json")
        || nextRun.artifacts.includes("chapter_script_cards.json")
      ) {
        await loadChapterScriptReviewState(nextRun.run_id);
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

  function clearFinalFeedbackDiagnosis() {
    setFinalFeedbackResult(null);
    setFinalFeedbackChapterId(null);
    setFinalFeedbackDraft("");
    setFinalFeedbackThinking("");
  }

  async function handleIntake() {
    setBusy(true);
    setError(null);
    setPlanMarkdown("");
    setAdaptationPlan(null);
    setChapterCards([]);
    setChapterReviews([]);
    setChapterScriptReviews([]);
    setOpenChapterId(null);
    setOpenScriptChapterId(null);
    setChatChapterId(null);
    setChatMode("chapter");
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
    setFinalFeedbackOpen(false);
    setFinalFeedbackText("");
    setFinalFeedbackDesired("");
    setFinalFeedbackResult(null);
    setActiveArtifactPanel(null);
    setGenerationRequested(false);
    setControls((current) => ({ ...current, generation_scope: [] }));
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
    if (!run || busy) {
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
    if (!run || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    setRun({ ...run, status: "regenerating_chapter", current_stage: "regenerate_chapter" });
    setChapterReviews((current) => current.map((item) => (
      item.review.chapter_id === chapterId
        ? {
            ...item,
            review: {
              ...item.review,
              status: "regenerating",
              approved_at: null,
              error: null,
            },
          }
        : item
    )));
    setTypedSummaries((current) => {
      const next = { ...current };
      delete next[chapterId];
      return next;
    });
    try {
      setPlanMarkdown("");
      setAdaptationPlan(null);
      setStoryBible(null);
      setStoryBibleMarkdown("");
      setChapterScriptReviews([]);
      setOpenScriptChapterId(null);
      setYamlText("");
      setReportMarkdown("");
      setValidationReport(null);
      setActiveArtifactPanel(null);
      setControls((current) => ({ ...current, generation_scope: [] }));
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
    setChatMode("chapter");
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

  async function handleOpenScriptChat(chapterId: string) {
    if (!run) {
      return;
    }
    setChatChapterId(chapterId);
    setChatMode("script");
    setActiveArtifactPanel(null);
    setAssistantDraft("");
    setVisibleThinking("");
    setToolEvents([]);
    try {
      const response = await getChapterScriptChatMessages(run.run_id, chapterId);
      setChatMessages(response.messages.map((message) => ({
        role: message.role === "assistant" ? "assistant" : "user",
        content: message.content,
      })));
    } catch {
      setChatMessages([]);
    }
  }

  async function handleSendChapterChat() {
    if (!run || busy || !chatChapterId || !chatInput.trim()) {
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
      const chatPath = chatMode === "script"
        ? "chapter-script-cards"
        : "chapter-cards";
      const response = await fetch(`${API_BASE_URL}/api/runs/${run.run_id}/${chatPath}/${chatChapterId}/chat/stream`, {
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
      let finalized = false;
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
            const name = String(payload.name ?? "tool");
            const status = String(payload.status ?? "ready");
            if (name !== "tool_registry" || status !== "disabled") {
              setToolEvents((current) => [...current, `${name}：${status}`]);
            }
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
            setVisibleThinking("");
            setToolEvents([]);
            finalized = true;
          }
          if (payload.type === "error") {
            throw new Error(String(payload.content ?? "Chapter chat failed."));
          }
        }
      }
      if (!finalized && collected) {
        setChatMessages((current) => [...current, { role: "assistant", content: collected }]);
        setAssistantDraft("");
        setVisibleThinking("");
        setToolEvents([]);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
      setAssistantDraft("");
      setVisibleThinking("");
      setToolEvents([]);
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerate() {
    if (!run) {
      return;
    }
    if (!controls.generation_scope.length) {
      setError("请先选择要生成剧本卡的章节。");
      return;
    }
    setBusy(true);
    setError(null);
    setYamlText("");
    setReportMarkdown("");
    setValidationReport(null);
    setActiveArtifactPanel(null);
    setChapterScriptReviews([]);
    setOpenScriptChapterId(null);
    setGenerationRequested(true);
    try {
      const nextRun = await generateRun(run.run_id, controls);
      setRun(
        nextRun.status === "planned"
          ? { ...nextRun, status: "generating_chapter_scripts", current_stage: "generate_chapter_script_cards" }
          : nextRun,
      );
      if (nextRun.status === "awaiting_script_review" || nextRun.artifacts.includes("chapter_script_reviews.json")) {
        await loadChapterScriptReviewState(nextRun.run_id);
        setGenerationRequested(false);
      }
    } catch (nextError) {
      setGenerationRequested(false);
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleApproveChapterScript(chapterId: string) {
    if (!run || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await approveChapterScript(run.run_id, chapterId);
      setChapterScriptReviews(response.items);
      setRun(await getRun(run.run_id));
      await refreshTasks();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleApproveAllChapterScripts() {
    if (!run) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await approveAllChapterScripts(run.run_id);
      setChapterScriptReviews(response.items);
      setRun(await getRun(run.run_id));
      await refreshTasks();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleRegenerateChapterScript(chapterId: string) {
    if (!run || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    setRun({ ...run, status: "regenerating_chapter_script", current_stage: "regenerate_chapter_script" });
    setChapterScriptReviews((current) => markScriptReviewRegenerating(current, chapterId));
    try {
      setYamlText("");
      setReportMarkdown("");
      setValidationReport(null);
      setFinalFeedbackOpen(false);
      setFinalFeedbackResult(null);
      setFinalFeedbackChapterId(null);
      setFinalFeedbackApplying(false);
      setFinalFeedbackMessages([]);
      setFinalFeedbackDraft("");
      setFinalFeedbackThinking("");
      setActiveArtifactPanel(null);
      const response = await regenerateChapterScript(run.run_id, chapterId);
      setChapterScriptReviews(response.items);
      await refreshTasks();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function handleContinuityMerge() {
    if (!run) {
      return;
    }
    setBusy(true);
    setError(null);
    setActiveArtifactPanel(null);
    setGenerationRequested(true);
    try {
      const nextRun = await continuityMerge(run.run_id);
      const mergeFinished = nextRun.status === "awaiting_final_review" || nextRun.artifacts.includes("script.yaml");
      setRun(
        mergeFinished
          ? nextRun
          : { ...nextRun, status: "merging_continuity", current_stage: "continuity_merge" },
      );
      await refreshTasks();
      if (mergeFinished) {
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
    if (!run || busy) {
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

  async function handleCreateFinalFeedback() {
    if (!run || busy || !finalFeedbackText.trim()) {
      return;
    }
    const complaint = finalFeedbackText.trim();
    const desiredChange = finalFeedbackDesired.trim();
    setBusy(true);
    setError(null);
    setFinalFeedbackDraft("");
    setFinalFeedbackThinking("");
    setFinalFeedbackResult(null);
    setFinalFeedbackChapterId(null);
    setFinalFeedbackApplying(false);
    setFinalFeedbackMessages((current) => [
      ...current,
      {
        role: "user",
        content: `${finalFeedbackCategoryLabel(finalFeedbackCategory)}：${complaint}${desiredChange ? `\n希望调整：${desiredChange}` : ""}`,
      },
    ]);
    try {
      const response = await fetch(`${API_BASE_URL}/api/runs/${run.run_id}/final-feedback/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: finalFeedbackCategory,
          complaint,
          desired_change: desiredChange,
        }),
      });
      if (!response.ok || !response.body) {
        throw new Error(response.ok ? "Streaming response is empty." : await response.text());
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let collected = "";
      let finalized = false;
      let diagnosisCommitted = false;
      let feedbackResponse: FinalFeedbackResponse | null = null;
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
            setFinalFeedbackThinking(String(payload.content ?? ""));
          }
          if (payload.type === "assistant_delta") {
            const chunk = String(payload.content ?? "");
            collected += chunk;
            setFinalFeedbackDraft(collected);
          }
          if (payload.type === "final_feedback") {
            const response = {
              feedback: payload.feedback as FinalFeedbackResponse["feedback"],
              suggested_chapter_id: (payload.suggested_chapter_id as string | null | undefined) ?? null,
              suggested_scene_id: (payload.suggested_scene_id as string | null | undefined) ?? null,
              message: String(payload.message ?? ""),
            };
            const diagnosisText = collected || response.message;
            feedbackResponse = response;
            setFinalFeedbackResult(response);
            setFinalFeedbackChapterId(
              response.feedback.target_type === "continuity"
                ? null
                : response.suggested_chapter_id,
            );
            if (diagnosisText && !diagnosisCommitted) {
              setFinalFeedbackMessages((current) => [...current, { role: "assistant", content: diagnosisText }]);
              setFinalFeedbackDraft("");
              setFinalFeedbackThinking("");
              diagnosisCommitted = true;
            }
          }
          if (payload.type === "final") {
            const content = collected || String(payload.content ?? "");
            if (content && !diagnosisCommitted) {
              setFinalFeedbackMessages((current) => [...current, { role: "assistant", content }]);
            }
            setFinalFeedbackDraft("");
            setFinalFeedbackThinking("");
            finalized = true;
          }
          if (payload.type === "error") {
            throw new Error(String(payload.content ?? "Final feedback chat failed."));
          }
        }
      }
      if (!finalized && collected && !diagnosisCommitted) {
        setFinalFeedbackMessages((current) => [...current, { role: "assistant", content: collected }]);
        setFinalFeedbackDraft("");
        setFinalFeedbackThinking("");
      }
      if (feedbackResponse?.feedback.target_type === "continuity") {
        await applyFinalFeedbackResponse(feedbackResponse, null);
      } else if (feedbackResponse?.suggested_chapter_id) {
        await applyFinalFeedbackResponse(feedbackResponse, feedbackResponse.suggested_chapter_id);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
      setFinalFeedbackDraft("");
      setFinalFeedbackThinking("");
    } finally {
      setBusy(false);
    }
  }

  async function handleApplyFinalFeedback() {
    if (!run || busy || finalFeedbackApplying || !finalFeedbackResult) {
      return;
    }
    const feedbackToApply = finalFeedbackResult;
    if (feedbackToApply.feedback.target_type !== "continuity" && !finalFeedbackChapterId) {
      setError("请先确认要重写的章节，再执行返修。");
      return;
    }
    setBusy(true);
    try {
      await applyFinalFeedbackResponse(
        feedbackToApply,
        feedbackToApply.feedback.target_type === "continuity" ? null : finalFeedbackChapterId,
      );
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function applyFinalFeedbackResponse(
    feedbackToApply: FinalFeedbackResponse,
    confirmedChapterId: string | null,
  ) {
    if (!run) {
      return;
    }
    if (feedbackToApply.feedback.target_type !== "continuity" && !confirmedChapterId) {
      throw new Error("请先确认要重写的章节，再执行返修。");
    }
    setFinalFeedbackApplying(true);
    setError(null);
    setGenerationRequested(true);
    if (confirmedChapterId) {
      setChapterScriptReviews((current) => markScriptReviewRegenerating(current, confirmedChapterId));
    }
    try {
      const response = await applyFinalFeedback(
        run.run_id,
        feedbackToApply.feedback.id,
        feedbackToApply.feedback.target_type === "continuity" ? null : confirmedChapterId,
      );
      setFinalFeedbackMessages((current) => [
        ...current,
        { role: "assistant", content: response.message },
      ]);
      setFinalFeedbackResult(null);
      setFinalFeedbackChapterId(null);
      const nextStatus = feedbackToApply.feedback.target_type === "continuity"
        ? "merging_continuity"
        : "regenerating_chapter_script";
      setRun({
        ...run,
        status: nextStatus,
        current_stage: nextStatus === "merging_continuity" ? "continuity_merge" : "regenerate_chapter_script",
      });
      await refreshTasks();
    } catch (nextError) {
      setGenerationRequested(false);
      setFinalFeedbackApplying(false);
      throw nextError;
    }
  }

  async function handleConfirmFinalScript() {
    if (!run || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const nextRun = await confirmFinalScript(run.run_id);
      setRun(nextRun);
      setFinalFeedbackOpen(false);
      await refreshTasks();
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
    const nextPlan = JSON.parse(nextPlanJson) as AdaptationPlan;
    const nextCards = JSON.parse(cardsText) as ChapterCard[];
    const nextBible = JSON.parse(bibleText) as StoryBible;
    setPlanMarkdown(nextPlanMarkdown);
    setAdaptationPlan(nextPlan);
    setChapterCards(nextCards);
    setStoryBible(nextBible);
    setStoryBibleMarkdown(bibleMarkdown);
    setControls((current) => {
      const validIndexes = nextCards.map((card) => card.chapter_index);
      const currentScope = normalizeGenerationScope(current.generation_scope, validIndexes);
      const recommendedScope = normalizeGenerationScope(
        nextBible.recommended_generation_scope.length
          ? nextBible.recommended_generation_scope
          : nextPlan.recommended_generation_scope,
        validIndexes,
      );
      return {
        ...current,
        generation_scope: currentScope.length ? currentScope : recommendedScope,
      };
    });
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
    <div className={artifactPanelOpen ? "workspace workspace-with-artifact" : "workspace workspace-compact"}>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <strong>Novel2Script</strong>
          <span>小说作者的剧本改编工作台</span>
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
          <button type="button" disabled={!chapterScriptReviews.length} onClick={() => openArtifactPanel("chapterScripts")}>
            章节剧本卡
          </button>
          <button type="button" disabled={!yamlText} onClick={() => openArtifactPanel("yaml")}>
            打开 YAML
          </button>
          <button type="button" disabled={!reportMarkdown && !validationReport} onClick={() => openArtifactPanel("report")}>
            查看报告
          </button>
          <button type="button" disabled={!artifactGroups.length} onClick={() => openArtifactPanel("downloads")}>
            下载产物
          </button>
          <button type="button" disabled={!run || !artifactGroups.length} onClick={() => openArtifactPanel("details")}>
            运行详情
          </button>
        </div>
        <a className="health-link" href={`${API_BASE_URL}/health`} target="_blank">
          服务状态
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
          <p>AI 剧本副编剧</p>
          <h1>把小说改成可表演、可追踪、可继续打磨的剧本初稿</h1>
          <div className="header-summary">
            <span>面向网文作者</span>
            <span>3 章以上小说输入</span>
            <span>最终产物为可编辑 YAML 剧本</span>
          </div>
          <WorkflowOverview
            approvedChapterCount={approvedChapterCount}
            approvedScriptCount={approvedScriptCount}
            chapterCount={chapterReviews.length || chapterCards.length || inputChapterEstimate}
            phase={phase}
            selectedScopeCount={controls.generation_scope.length}
            totalScriptScenes={totalScriptScenes}
            yamlReady={Boolean(yamlText)}
          />
        </section>

        <section className="message-list" aria-label="副编剧对话流">
          <AssistantMessage title="我会先读小说，再给你一份改编计划">
            <p>
              我不会一上来直接交 YAML。先把章节、人物、线索和改编风险梳理出来，
              等你确认剧本类型、改编尺度和保留内容后，再生成可编辑剧本。
            </p>
          </AssistantMessage>

          <UserMessage title="小说输入">
            <InputGuidance chapterEstimate={inputChapterEstimate} />
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
                  canReview={canReviewChapters}
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
              <GenerationScopeSelector
                chapterCards={chapterCards}
                recommendedScope={
                  storyBible?.recommended_generation_scope.length
                    ? storyBible.recommended_generation_scope
                    : adaptationPlan?.recommended_generation_scope ?? []
                }
                selectedScope={controls.generation_scope}
                onChange={(scope) => updateControl("generation_scope", scope)}
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
                  {generationRequested || run?.status === "generating_chapter_scripts" ? "正在生成剧本卡..." : "生成每章剧本卡"}
                </button>
              </div>
            </UserMessage>
          ) : null}

          {chapterScriptReviews.length ? (
            <AssistantMessage title="章节剧本卡确认">
              <ChapterScriptReviewWorkbench
                allApproved={allScriptsApproved}
                busy={busy}
                canApprove={canReviewScripts}
                canMerge={canContinuityMerge}
                expanded={scriptReviewsExpanded}
                filter={scriptReviewFilter}
                items={chapterScriptReviews}
                onApprove={handleApproveChapterScript}
                onApproveAll={handleApproveAllChapterScripts}
                onDiscuss={handleOpenScriptChat}
                onFilterChange={setScriptReviewFilter}
                onMerge={handleContinuityMerge}
                onRegenerate={handleRegenerateChapterScript}
                onToggleExpanded={() => setScriptReviewsExpanded((current) => !current)}
                openChapterId={openScriptChapterId}
                setOpenChapterId={setOpenScriptChapterId}
              />
            </AssistantMessage>
          ) : null}

          {completed ? (
            <AssistantMessage title="剧本已生成">
              <div className="completion-summary">
                <div>
                  <strong>YAML 初稿已就绪</strong>
                  <span>已标记来源、AI 新增内容、修改建议和生产提示。</span>
                </div>
                <div>
                  <strong>{totalScriptScenes || "多"} 场戏</strong>
                  <span>来自已通过的章节剧本卡，可继续回退修改。</span>
                </div>
              </div>
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
          chapterId={chatChapterId}
          mode={chatMode}
          summary={chatMode === "script" ? activeScriptChatChapter?.script_card?.summary : activeChatChapter?.card?.summary}
          title={chatMode === "script" ? activeScriptChatChapter?.chapter.title : activeChatChapter?.chapter.title}
          wordCount={chatMode === "script" ? activeScriptChatChapter?.chapter.char_count : activeChatChapter?.chapter.char_count}
          input={chatInput}
          messages={chatMessages}
          onChangeInput={setChatInput}
          onClose={() => setChatChapterId(null)}
          onRegenerate={chatMode === "script" ? handleRegenerateChapterScript : handleRegenerateChapter}
          regenerating={Boolean(
            chatMode === "script"
              ? activeScriptChatChapter?.review.status === "regenerating"
              : activeChatChapter?.review.status === "regenerating"
          )}
          onSend={handleSendChapterChat}
          toolEvents={toolEvents}
          visibleThinking={visibleThinking}
        />
      ) : activeArtifactPanel ? (
        <ArtifactPanelView
          activePanel={activeArtifactPanel}
          artifactGroups={artifactGroups}
          busy={busy}
          canValidate={canValidate}
          chapterCards={chapterCards}
          chapterScriptReviews={chapterScriptReviews}
          finalFeedbackCategory={finalFeedbackCategory}
          finalFeedbackApplying={finalFeedbackApplying}
          finalFeedbackChapterId={finalFeedbackChapterId}
          finalFeedbackDesired={finalFeedbackDesired}
          finalFeedbackDraft={finalFeedbackDraft}
          finalFeedbackMessages={finalFeedbackMessages}
          finalFeedbackOpen={finalFeedbackOpen}
          finalFeedbackResult={finalFeedbackResult}
          finalFeedbackText={finalFeedbackText}
          finalFeedbackThinking={finalFeedbackThinking}
          handleDownloadEditedYaml={handleDownloadEditedYaml}
          handleApplyFinalFeedback={handleApplyFinalFeedback}
          handleConfirmFinalScript={handleConfirmFinalScript}
          handleCreateFinalFeedback={handleCreateFinalFeedback}
          handleValidateYaml={handleValidateYaml}
          reportMarkdown={reportMarkdown}
          run={run}
          schema={schema}
          setActivePanel={setActiveArtifactPanel}
          setFinalFeedbackCategory={(category) => {
            setFinalFeedbackCategory(category);
            clearFinalFeedbackDiagnosis();
          }}
          setFinalFeedbackChapterId={setFinalFeedbackChapterId}
          setFinalFeedbackDesired={(value) => {
            setFinalFeedbackDesired(value);
            clearFinalFeedbackDiagnosis();
          }}
          setFinalFeedbackOpen={setFinalFeedbackOpen}
          setFinalFeedbackText={(value) => {
            setFinalFeedbackText(value);
            clearFinalFeedbackDiagnosis();
          }}
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

function WorkflowOverview({
  approvedChapterCount,
  approvedScriptCount,
  chapterCount,
  phase,
  selectedScopeCount,
  totalScriptScenes,
  yamlReady,
}: {
  approvedChapterCount: number;
  approvedScriptCount: number;
  chapterCount: number;
  phase: ConversationPhase;
  selectedScopeCount: number;
  totalScriptScenes: number;
  yamlReady: boolean;
}) {
  const steps = [
    {
      label: "导入小说",
      detail: chapterCount ? `已识别约 ${chapterCount} 章` : "等待 3 章以上原文",
      active: true,
      done: chapterCount >= 3 || phase !== "idle",
    },
    {
      label: "确认理解",
      detail: approvedChapterCount ? `已通过 ${approvedChapterCount} 章` : "先确认 AI 是否读懂",
      active: phase === "analyzing" || phase === "reviewing",
      done: approvedChapterCount > 0,
    },
    {
      label: "设定改编",
      detail: selectedScopeCount ? `已选择 ${selectedScopeCount} 章生成` : "选择剧本类型和范围",
      active: phase === "planned",
      done: selectedScopeCount > 0,
    },
    {
      label: "打磨 YAML",
      detail: yamlReady ? `${totalScriptScenes || "多"} 场戏可编辑` : approvedScriptCount ? `已通过 ${approvedScriptCount} 张剧本卡` : "等待最终稿",
      active: phase === "generating" || phase === "completed",
      done: yamlReady,
    },
  ];

  return (
    <div className="workflow-overview" aria-label="当前改编进度">
      {steps.map((step, index) => (
        <div
          className={`workflow-step ${step.active ? "active" : ""} ${step.done ? "done" : ""}`}
          key={step.label}
        >
          <span>{index + 1}</span>
          <strong>{step.label}</strong>
          <small>{step.detail}</small>
        </div>
      ))}
    </div>
  );
}

function InputGuidance({ chapterEstimate }: { chapterEstimate: number }) {
  return (
    <div className="input-guidance">
      <div>
        <strong>{chapterEstimate >= 3 ? "章节数量可用" : "至少需要 3 章"}</strong>
        <span>当前约 {chapterEstimate || 0} 章，长篇输入会先拆章理解。</span>
      </div>
      <div>
        <strong>作者先确认</strong>
        <span>章节理解和剧本卡都可以审核，不满意再重读或重写。</span>
      </div>
      <div>
        <strong>YAML 可编辑</strong>
        <span>最终稿可校验、下载，也能继续反馈修改。</span>
      </div>
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
  canReview,
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
  canReview: boolean;
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
        <button type="button" disabled={!canReview || !items.length || busy} onClick={onApproveAll}>
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
            busy={busy}
            item={item}
            key={item.review.chapter_id}
            onApprove={onApprove}
            onDiscuss={onDiscuss}
            onRegenerate={onRegenerate}
            open={openChapterId === item.review.chapter_id}
            setOpen={(nextOpen) => setOpenChapterId(nextOpen ? item.review.chapter_id : null)}
            typedSummary={typedSummaries[item.review.chapter_id]}
            canReview={canReview}
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
  busy,
  canReview,
  item,
  onApprove,
  onDiscuss,
  onRegenerate,
  open,
  setOpen,
  typedSummary,
}: {
  busy: boolean;
  canReview: boolean;
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
  const cardLocked = item.review.status === "pending"
    || item.review.status === "reading"
    || item.review.status === "regenerating";
  return (
    <article className={`review-card ${reviewStatusClass(item.review.status)}`}>
      <div className="review-card-head">
        <div>
          <strong>
            第 {item.chapter.index} 章 · {item.chapter.title}
          </strong>
          <span>原文 {item.chapter.char_count} 字 · {reviewStatusLabel(item.review.status)}</span>
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
        <button type="button" disabled={!canReview || !card || cardLocked} onClick={() => onDiscuss(chapterId)}>
          讨论/修改理解
        </button>
        <button type="button" disabled={!canReview || busy || !card || cardLocked || item.review.status === "approved"} onClick={() => onApprove(chapterId)}>
          通过
        </button>
        <button type="button" disabled={!canReview || busy || !card || cardLocked} onClick={() => onRegenerate(chapterId)}>
          重新理解
        </button>
      </div>
    </article>
  );
}

function ChapterScriptReviewWorkbench({
  allApproved,
  busy,
  canApprove,
  canMerge,
  expanded,
  filter,
  items,
  onApprove,
  onApproveAll,
  onDiscuss,
  onFilterChange,
  onMerge,
  onRegenerate,
  onToggleExpanded,
  openChapterId,
  setOpenChapterId,
}: {
  allApproved: boolean;
  busy: boolean;
  canApprove: boolean;
  canMerge: boolean;
  expanded: boolean;
  filter: ReviewFilter;
  items: ChapterScriptReviewItem[];
  onApprove: (chapterId: string) => void;
  onApproveAll: () => void;
  onDiscuss: (chapterId: string) => void;
  onFilterChange: (filter: ReviewFilter) => void;
  onMerge: () => void;
  onRegenerate: (chapterId: string) => void;
  onToggleExpanded: () => void;
  openChapterId: string | null;
  setOpenChapterId: (chapterId: string | null) => void;
}) {
  const filtered = filterScriptReviewItems(items, filter);
  const visibleItems = expanded ? filtered : filtered.slice(0, 5);
  const readyCount = items.filter((item) => item.review.status === "ready" || item.review.status === "approved").length;
  const approvedCount = items.filter((item) => item.review.status === "approved").length;
  return (
    <div className="review-workbench script-workbench">
      <div className="review-toolbar">
        <div>
          <span>已生成 {readyCount}/{items.length} 张剧本卡</span>
          <strong>已通过 {approvedCount}/{items.length} 张</strong>
        </div>
        <div className="segmented-control" role="group" aria-label="剧本卡筛选">
          <button className={filter === "all" ? "active" : ""} type="button" onClick={() => onFilterChange("all")}>
            全部
          </button>
          <button className={filter === "pending" ? "active" : ""} type="button" onClick={() => onFilterChange("pending")}>
            未通过
          </button>
          <button className={filter === "attention" ? "active" : ""} type="button" onClick={() => onFilterChange("attention")}>
            已重写
          </button>
        </div>
      </div>
      <div className="review-actions">
        <button type="button" disabled={!canApprove || !items.length || busy} onClick={onApproveAll}>
          全部通过
        </button>
        <button type="button" disabled={!canMerge || busy} onClick={onMerge}>
          连贯性合成并导出 YAML
        </button>
        <button type="button" disabled={filtered.length <= 5} onClick={onToggleExpanded}>
          {expanded ? "收起剧本卡" : "展开全部"}
        </button>
      </div>
      <div className="review-grid" data-testid="chapter-script-review-grid">
        {visibleItems.map((item) => (
          <ChapterScriptReviewCard
            busy={busy}
            canApprove={canApprove}
            item={item}
            key={item.review.chapter_id}
            onApprove={onApprove}
            onDiscuss={onDiscuss}
            onRegenerate={onRegenerate}
            open={openChapterId === item.review.chapter_id}
            setOpen={(nextOpen) => setOpenChapterId(nextOpen ? item.review.chapter_id : null)}
          />
        ))}
      </div>
      {!allApproved ? (
        <p className="review-hint">最终 YAML 只会由已通过的章节剧本卡合成。</p>
      ) : (
        <p className="review-hint success-text">所有章节剧本卡已通过，可以进入连贯性合成。</p>
      )}
    </div>
  );
}

function ChapterScriptReviewCard({
  busy,
  canApprove,
  item,
  onApprove,
  onDiscuss,
  onRegenerate,
  open,
  setOpen,
}: {
  busy: boolean;
  canApprove: boolean;
  item: ChapterScriptReviewItem;
  onApprove: (chapterId: string) => void;
  onDiscuss: (chapterId: string) => void;
  onRegenerate: (chapterId: string) => void;
  open: boolean;
  setOpen: (open: boolean) => void;
}) {
  const card = item.script_card;
  const chapterId = item.review.chapter_id;
  const cardLocked = item.review.status === "pending"
    || item.review.status === "generating"
    || item.review.status === "regenerating";
  const statusLabel = item.review.status === "ready" && item.review.revision_count > 0
    ? "已重写，待确认"
    : scriptReviewStatusLabel(item.review.status);
  return (
    <article className={`review-card script-card ${scriptReviewStatusClass(item.review.status)}`}>
      <div className="review-card-head">
        <div>
          <strong>
            第 {item.chapter.index} 章剧本卡 · {item.chapter.title}
          </strong>
          <span>原文 {item.chapter.char_count} 字 · {statusLabel}</span>
        </div>
        <span className="revision-pill">
          {item.review.status === "regenerating" ? "正在重写" : `已重写 ${item.review.revision_count}`}
        </span>
      </div>
      {card ? (
        <>
          <p className="review-summary">{card.summary}</p>
          <div className="review-tags">
            <span>{card.scenes.length} 场戏</span>
            <span>{card.format_type}</span>
            {card.absorbed_feedback.length ? <span>已吸收反馈</span> : null}
          </div>
          {open ? (
            <div className="review-details">
              <DetailList title="开场承接" items={[card.opening_bridge]} />
              <DetailList title="结尾钩子" items={[card.ending_hook]} />
              <DetailList title="衔接点" items={card.continuity_links} />
              <DetailList title="已吸收反馈" items={card.absorbed_feedback} />
              <div className="detail-list">
                <span>场景</span>
                {card.scenes.map((scene) => (
                  <div className="script-scene-preview" key={scene.id}>
                    <strong>{scene.id} · {scene.title}</strong>
                    <p>{scene.purpose}</p>
                    <small>冲突：{scene.conflict}</small>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <p className="review-summary">这一章剧本卡还在生成中。</p>
      )}
      {item.review.error ? <p className="error-text">{item.review.error}</p> : null}
      <div className="review-card-actions">
        <button type="button" disabled={!card} onClick={() => setOpen(!open)}>
          {open ? "收起详情" : "查看剧本卡"}
        </button>
        <button type="button" disabled={!card || cardLocked} onClick={() => onDiscuss(chapterId)}>
          讨论/修改剧本
        </button>
        <button type="button" disabled={!canApprove || busy || !card || cardLocked || item.review.status === "approved"} onClick={() => onApprove(chapterId)}>
          通过
        </button>
        <button type="button" disabled={!canApprove || busy || !card || cardLocked} onClick={() => onRegenerate(chapterId)}>
          {item.review.status === "regenerating" ? "重写中..." : "重写本章"}
        </button>
      </div>
    </article>
  );
}

function ChapterChatPanel({
  assistantDraft,
  busy,
  chapterId,
  mode,
  regenerating,
  summary,
  title,
  wordCount,
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
  chapterId: string;
  mode: ChatMode;
  regenerating: boolean;
  summary?: string;
  title?: string;
  wordCount?: number;
  input: string;
  messages: Array<{ role: "user" | "assistant"; content: string }>;
  onChangeInput: (value: string) => void;
  onClose: () => void;
  onRegenerate: (chapterId: string) => void;
  onSend: () => void;
  toolEvents: string[];
  visibleThinking: string;
}) {
  const hasDiscussion = messages.some((message) => message.role === "user");
  const regenerateLabel = mode === "script"
    ? regenerating ? "重写中..." : hasDiscussion ? "带着讨论重写本章剧本卡" : "重写本章剧本卡"
    : regenerating ? "重读中..." : hasDiscussion ? "带着讨论重新理解" : "重新理解本章";
  return (
    <aside className="chapter-chat-panel" data-testid="chapter-chat-panel">
      <div className="artifact-header">
        <div>
          <span>{mode === "script" ? "剧本卡讨论" : "章节讨论"}</span>
          <strong>{title ?? "章节"}</strong>
        </div>
        <button type="button" onClick={onClose}>
          关闭
        </button>
      </div>
      <div className="chapter-chat-context">
        {summary ? (
          <>
            <span>{chapterId} · 原文 {wordCount ?? 0} 字</span>
            <p>{summary}</p>
            <button type="button" disabled={busy || regenerating} onClick={() => onRegenerate(chapterId)}>
              {regenerateLabel}
            </button>
          </>
        ) : (
          <p>{mode === "script" ? "等待章节剧本卡生成。" : "等待章节理解卡生成。"}</p>
        )}
      </div>
      <div className="chapter-chat-messages" aria-label="章节聊天消息">
        {messages.length ? messages.map((message, index) => (
          <div className={`chapter-chat-message ${message.role}`} key={`${message.role}-${index}`}>
            <span>{message.role === "assistant" ? "AI" : "你"}</span>
            <p>{message.content}</p>
          </div>
        )) : (
          <div className="hint-card">先和 AI 说清楚哪里不合你意。讨论确认后，可以带着这段上下文重新理解或重写本章。</div>
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
          <span>原文总字数</span>
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
              {card.title} · 原文 {card.char_count} 字
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

function GenerationScopeSelector({
  chapterCards,
  onChange,
  recommendedScope,
  selectedScope,
}: {
  chapterCards: ChapterCard[];
  onChange: (scope: number[]) => void;
  recommendedScope: number[];
  selectedScope: number[];
}) {
  const validIndexes = chapterCards.map((card) => card.chapter_index);
  const recommended = normalizeGenerationScope(recommendedScope, validIndexes);
  const selected = normalizeGenerationScope(selectedScope, validIndexes);
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");

  function toggleChapter(index: number) {
    const next = selected.includes(index)
      ? selected.filter((item) => item !== index)
      : [...selected, index];
    onChange(normalizeGenerationScope(next, validIndexes));
  }

  function selectFirst(count: number) {
    onChange(validIndexes.slice(0, count));
  }

  function applyRange() {
    const start = Number(rangeStart);
    const end = Number(rangeEnd || rangeStart);
    if (!Number.isInteger(start) || !Number.isInteger(end)) {
      return;
    }
    const min = Math.min(start, end);
    const max = Math.max(start, end);
    onChange(validIndexes.filter((index) => index >= min && index <= max));
  }

  return (
    <div className="generation-scope-card">
      <div className="scope-card-head">
        <div>
          <span>生成范围</span>
          <strong>{selected.length ? `已选择第 ${selected.join(", ")} 章` : "请选择要生成剧本卡的章节"}</strong>
        </div>
        <div className="scope-actions">
          <button type="button" disabled={!validIndexes.length} onClick={() => selectFirst(3)}>
            前 3 章
          </button>
          <button type="button" disabled={validIndexes.length < 5} onClick={() => selectFirst(5)}>
            前 5 章
          </button>
          <button type="button" disabled={!recommended.length} onClick={() => onChange(recommended)}>
            采用 AI 推荐
          </button>
          <button type="button" disabled={!validIndexes.length} onClick={() => onChange(validIndexes)}>
            全选
          </button>
        </div>
      </div>
      <div className="scope-range-row">
        <span>范围选择</span>
        <input
          inputMode="numeric"
          min={1}
          placeholder="起始章"
          type="number"
          value={rangeStart}
          onChange={(event) => setRangeStart(event.target.value)}
        />
        <input
          inputMode="numeric"
          min={1}
          placeholder="结束章"
          type="number"
          value={rangeEnd}
          onChange={(event) => setRangeEnd(event.target.value)}
        />
        <button type="button" disabled={!rangeStart.trim()} onClick={applyRange}>
          应用范围
        </button>
      </div>
      <div className="scope-chip-grid" role="group" aria-label="选择生成章节">
        {chapterCards.map((card) => {
          const active = selected.includes(card.chapter_index);
          const isRecommended = recommended.includes(card.chapter_index);
          return (
            <button
              className={active ? "scope-chip active" : "scope-chip"}
              key={card.chapter_id}
              type="button"
              onClick={() => toggleChapter(card.chapter_index)}
            >
              <strong>第 {card.chapter_index} 章</strong>
              <span>{card.title}</span>
              {isRecommended ? <small>AI 推荐</small> : null}
            </button>
          );
        })}
      </div>
      <p className="scope-hint">
        AI 只负责推荐，最终生成哪几章由你决定。后续 YAML 会由这些章节剧本卡合成。
      </p>
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
  busy,
  canValidate,
  chapterCards,
  chapterScriptReviews,
  finalFeedbackCategory,
  finalFeedbackApplying,
  finalFeedbackChapterId,
  finalFeedbackDesired,
  finalFeedbackDraft,
  finalFeedbackMessages,
  finalFeedbackOpen,
  finalFeedbackResult,
  finalFeedbackText,
  finalFeedbackThinking,
  handleDownloadEditedYaml,
  handleApplyFinalFeedback,
  handleConfirmFinalScript,
  handleCreateFinalFeedback,
  handleValidateYaml,
  reportMarkdown,
  run,
  schema,
  setActivePanel,
  setFinalFeedbackCategory,
  setFinalFeedbackChapterId,
  setFinalFeedbackDesired,
  setFinalFeedbackOpen,
  setFinalFeedbackText,
  setYamlText,
  storyBible,
  storyBibleMarkdown,
  validationReport,
  yamlText,
}: {
  activePanel: ArtifactPanel;
  artifactGroups: { title: string; items: string[] }[];
  busy: boolean;
  canValidate: boolean;
  chapterCards: ChapterCard[];
  chapterScriptReviews: ChapterScriptReviewItem[];
  finalFeedbackCategory: "continuity" | "script_point" | "chapter_and_continuity";
  finalFeedbackApplying: boolean;
  finalFeedbackChapterId: string | null;
  finalFeedbackDesired: string;
  finalFeedbackDraft: string;
  finalFeedbackMessages: Array<{ role: "user" | "assistant"; content: string }>;
  finalFeedbackOpen: boolean;
  finalFeedbackResult: FinalFeedbackResponse | null;
  finalFeedbackText: string;
  finalFeedbackThinking: string;
  handleDownloadEditedYaml: () => void;
  handleApplyFinalFeedback: () => void;
  handleConfirmFinalScript: () => void;
  handleCreateFinalFeedback: () => void;
  handleValidateYaml: () => void;
  reportMarkdown: string;
  run: RunInfo | null;
  schema: Record<string, unknown> | null;
  setActivePanel: (panel: ArtifactPanel | null) => void;
  setFinalFeedbackCategory: (category: "continuity" | "script_point" | "chapter_and_continuity") => void;
  setFinalFeedbackChapterId: (chapterId: string | null) => void;
  setFinalFeedbackDesired: (value: string) => void;
  setFinalFeedbackOpen: (open: boolean) => void;
  setFinalFeedbackText: (value: string) => void;
  setYamlText: (value: string) => void;
  storyBible: StoryBible | null;
  storyBibleMarkdown: string;
  validationReport: ValidationReport | null;
  yamlText: string;
}) {
  const totalScenes = chapterScriptReviews.reduce((sum, item) => sum + (item.script_card?.scenes.length ?? 0), 0);
  const approvedScriptCount = chapterScriptReviews.filter((item) => item.review.status === "approved").length;
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
        {(["chapterCards", "chapterScripts", "storyBible", "yaml", "report", "downloads", "details"] as ArtifactPanel[]).map((panel) => (
          <button
            className={activePanel === panel ? "active" : ""}
            disabled={
              (panel === "chapterCards" && !chapterCards.length)
              || (panel === "chapterScripts" && !chapterScriptReviews.length)
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
                    {card.chapter_id} · {card.title} · 原文 {card.char_count} 字
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
      {activePanel === "chapterScripts" ? (
        <div className="artifact-body">
          {chapterScriptReviews.length ? (
            <div className="chapter-card-list">
              {chapterScriptReviews.map((item) => (
                <div className="chapter-card-item" key={item.review.chapter_id}>
                  <strong>
                    {item.review.chapter_id} · {item.chapter.title} · {scriptReviewStatusLabel(item.review.status)}
                  </strong>
                  <p>{item.script_card?.summary ?? "剧本卡尚未生成。"}</p>
                  {item.script_card ? (
                    <small>
                      场景：{item.script_card.scenes.map((scene) => `${scene.id} ${scene.title}`).join(" / ")}
                    </small>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <div className="hint-card">生成每章剧本卡后，这里会显示结构化剧本卡。</div>
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
              <div className="yaml-status-bar">
                <div>
                  <span>最终稿</span>
                  <strong>YAML 剧本初稿</strong>
                </div>
                <div>
                  <span>章节剧本卡</span>
                  <strong>{approvedScriptCount}/{chapterScriptReviews.length || 0} 已通过</strong>
                </div>
                <div>
                  <span>场景</span>
                  <strong>{totalScenes || "待统计"}</strong>
                </div>
                <div>
                  <span>校验</span>
                  <strong>{validationReport ? (validationReport.valid ? "已通过" : "需调整") : "待校验"}</strong>
                </div>
              </div>
              <div className="final-review-card">
                <div>
                  <span>最终确认</span>
                  <strong>这份 YAML 来自已通过章节剧本卡和连贯性合成</strong>
                  <p>可以只重做跨章合成，也可以只改某一章后自动合成；如果某章内容和前后过渡都不对，就选择两者一起修。</p>
                </div>
                <div className="inline-actions">
                  <button type="button" disabled={busy} onClick={handleConfirmFinalScript}>
                    确认剧本
                  </button>
                  <button type="button" onClick={() => setFinalFeedbackOpen(true)}>
                    剧本不满意
                  </button>
                </div>
                {finalFeedbackOpen ? (
                  <div className="feedback-box">
                    <div className="segmented-control" role="group" aria-label="最终返修类型">
                      <button
                        className={finalFeedbackCategory === "continuity" ? "active" : ""}
                        disabled={busy || finalFeedbackApplying}
                        type="button"
                        onClick={() => setFinalFeedbackCategory("continuity")}
                      >
                        连贯性不满意
                      </button>
                      <button
                        className={finalFeedbackCategory === "script_point" ? "active" : ""}
                        disabled={busy || finalFeedbackApplying}
                        type="button"
                        onClick={() => setFinalFeedbackCategory("script_point")}
                      >
                        某个剧本点不满意
                      </button>
                      <button
                        className={finalFeedbackCategory === "chapter_and_continuity" ? "active" : ""}
                        disabled={busy || finalFeedbackApplying}
                        type="button"
                        onClick={() => setFinalFeedbackCategory("chapter_and_continuity")}
                      >
                        章节和连贯性都不满意
                      </button>
                    </div>
                    <div className="feedback-chat-log">
                      {finalFeedbackMessages.length ? finalFeedbackMessages.map((message, index) => (
                        <div className={`chapter-chat-message ${message.role}`} key={`${message.role}-${index}`}>
                          <span>{message.role === "assistant" ? "AI" : "你"}</span>
                          <p>{message.content}</p>
                        </div>
                      )) : (
                        <div className="hint-card">
                          先告诉 AI 成品哪里不对。AI 会判断是只重做连贯性，还是先重写目标章节，再自动重新合成。
                        </div>
                      )}
                      {finalFeedbackThinking ? (
                        <div className="visible-thinking">
                          <span>思考摘要</span>
                          <p>{finalFeedbackThinking}</p>
                        </div>
                      ) : null}
                      {finalFeedbackDraft ? (
                        <div className="chapter-chat-message assistant streaming">
                          <span>AI</span>
                          <p>{finalFeedbackDraft}</p>
                        </div>
                      ) : null}
                    </div>
                    <textarea
                      disabled={busy || finalFeedbackApplying}
                      value={finalFeedbackText}
                      onChange={(event) => setFinalFeedbackText(event.target.value)}
                      placeholder="说明哪里不满意，例如：第二章和第三章之间过渡太突然，或者第三章对白太解释。"
                    />
                    <textarea
                      disabled={busy || finalFeedbackApplying}
                      value={finalFeedbackDesired}
                      onChange={(event) => setFinalFeedbackDesired(event.target.value)}
                      placeholder="希望怎么改，例如：更忠实原文、减少解释、加强冲突。"
                    />
                    <div className="inline-actions">
                      <button type="button" disabled={busy || !finalFeedbackText.trim() || finalFeedbackApplying} onClick={handleCreateFinalFeedback}>
                        发送给 AI 诊断
                      </button>
                      <button
                        type="button"
                        disabled={
                          busy
                          ||
                          !finalFeedbackResult
                          || finalFeedbackApplying
                          || (
                            finalFeedbackResult.feedback.target_type !== "continuity"
                            && !finalFeedbackChapterId
                          )
                        }
                        onClick={handleApplyFinalFeedback}
                      >
                        {finalFeedbackApplying
                          ? "正在回退处理..."
                          : finalFeedbackResult
                            ? finalFeedbackResult.feedback.target_type === "continuity"
                              ? "带着反馈重新合成"
                              : finalFeedbackResult.feedback.target_type === "chapter_and_continuity"
                                ? "重写章节并重新合成"
                                : "确认并重写对应章节"
                            : finalFeedbackCategory === "continuity"
                              ? "AI 诊断后自动重新合成"
                              : finalFeedbackCategory === "chapter_and_continuity"
                                ? "AI 定位后自动重写并合成"
                                : "AI 定位后自动重写"}
                      </button>
                    </div>
                    {finalFeedbackResult ? (
                      <div className="notice">
                        <strong>{finalFeedbackResult.message}</strong>
                        <div>
                          建议定位：
                          {finalFeedbackResult.suggested_chapter_id ?? "连贯性合成阶段"}
                          {finalFeedbackResult.suggested_scene_id ? ` / ${finalFeedbackResult.suggested_scene_id}` : ""}
                        </div>
                        {finalFeedbackResult.feedback.target_type !== "continuity" ? (
                          <label className="feedback-target-select">
                            <span>确认要重写的章节</span>
                            <select
                              disabled={busy || finalFeedbackApplying}
                              value={finalFeedbackChapterId ?? ""}
                              onChange={(event) => setFinalFeedbackChapterId(event.target.value || null)}
                            >
                              <option value="">请选择章节</option>
                              {chapterScriptReviews.map((item) => (
                                <option key={item.review.chapter_id} value={item.review.chapter_id}>
                                  {item.review.chapter_id} · {item.chapter.title}
                                  {item.review.chapter_id === finalFeedbackResult.suggested_chapter_id ? "（AI 建议）" : ""}
                                </option>
                              ))}
                            </select>
                            <small>AI 只是建议定位，真正回退哪一章由作者确认。</small>
                          </label>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <YamlEditor value={yamlText} schema={schema} onChange={setYamlText} />
              <div className="inline-actions">
                <button type="button" disabled={busy || !canValidate} onClick={handleValidateYaml}>
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

function estimateChapterCount(text: string): number {
  const matches = text.match(/(?:^|\n)\s*(第[一二三四五六七八九十百千万零〇\d]+[章节回]|Chapter\s+\d+)/gi);
  return matches?.length ?? 0;
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
  if (yamlText && run.status === "awaiting_final_review") {
    return "completed";
  }
  if (run.status === "awaiting_chapter_review" || run.status === "regenerating_chapter") {
    return "reviewing";
  }
  if (run.status === "awaiting_script_review" || run.status === "regenerating_chapter_script") {
    return "generating";
  }
  if (run.status === "reading_chapters") {
    return "analyzing";
  }
  if (run.status === "planning") {
    return "analyzing";
  }
  if (run.status === "generating_chapter_scripts" || run.status === "merging_continuity") {
    return "generating";
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
    completed: 5,
    failed: 0,
  };
  return indexes[phase];
}

function panelTitle(panel: ArtifactPanel): string {
  const labels: Record<ArtifactPanel, string> = {
    chapterCards: "章节理解卡",
    chapterScripts: "章节剧本卡",
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
    return items.filter((item) => item.review.revision_count > 0);
  }
  return items;
}

function filterScriptReviewItems(items: ChapterScriptReviewItem[], filter: ReviewFilter): ChapterScriptReviewItem[] {
  if (filter === "pending") {
    return items.filter((item) => item.review.status !== "approved");
  }
  if (filter === "attention") {
    return items.filter((item) => item.review.status === "failed" || item.review.revision_count > 0);
  }
  return items;
}

function markScriptReviewRegenerating(
  items: ChapterScriptReviewItem[],
  chapterId: string,
): ChapterScriptReviewItem[] {
  return items.map((item) => (
    item.review.chapter_id === chapterId
      ? {
          ...item,
          review: {
            ...item.review,
            status: "regenerating",
            approved_at: null,
            error: null,
          },
        }
      : item
  ));
}

function finalFeedbackCategoryLabel(
  category: "continuity" | "script_point" | "chapter_and_continuity",
): string {
  const labels = {
    continuity: "连贯性不满意",
    script_point: "具体剧本点不满意",
    chapter_and_continuity: "章节和连贯性都不满意",
  };
  return labels[category];
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

function scriptReviewStatusLabel(status: ChapterScriptReviewItem["review"]["status"]): string {
  const labels: Record<ChapterScriptReviewItem["review"]["status"], string> = {
    pending: "排队中",
    generating: "生成中",
    ready: "待确认",
    approved: "已通过",
    regenerating: "重写中",
    failed: "需处理",
  };
  return labels[status];
}

function scriptReviewStatusClass(status: ChapterScriptReviewItem["review"]["status"]): string {
  if (status === "approved") {
    return "approved";
  }
  if (status === "failed") {
    return "failed";
  }
  if (status === "generating" || status === "regenerating") {
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
    generating_chapter_scripts: "生成剧本卡",
    awaiting_script_review: "待确认剧本卡",
    regenerating_chapter_script: "重写剧本卡",
    merging_continuity: "合成中",
    awaiting_final_review: "待最终确认",
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

function normalizeGenerationScope(scope: number[], validIndexes: number[]): number[] {
  const valid = new Set(validIndexes);
  return Array.from(new Set(scope.filter((index) => valid.has(index)))).sort((a, b) => a - b);
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
