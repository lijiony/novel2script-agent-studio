export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type RunStage = {
  name: string;
  status: "pending" | "running" | "succeeded" | "failed";
  message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

export type RunStatus =
  | "queued"
  | "running"
  | "reading_chapters"
  | "awaiting_chapter_review"
  | "regenerating_chapter"
  | "planning"
  | "planned"
  | "generating"
  | "validating"
  | "repairing"
  | "exporting"
  | "succeeded"
  | "failed_validation"
  | "failed_llm"
  | "failed_internal";

export type RunInfo = {
  run_id: string;
  status: RunStatus;
  current_stage: string | null;
  stages: RunStage[];
  artifacts: string[];
  error?: string | null;
};

export type RunListItem = {
  run_id: string;
  title: string;
  status: RunStatus;
  current_stage: string | null;
  artifacts: string[];
  created_at: string;
  updated_at: string;
};

export type ValidationIssue = {
  severity: "info" | "warning" | "error";
  path: string;
  message: string;
  suggestion?: string | null;
};

export type ValidationReport = {
  valid: boolean;
  summary: string;
  issues: ValidationIssue[];
};

export type ScriptFormat =
  | "film"
  | "short_drama"
  | "stage_play"
  | "radio_drama"
  | "animation"
  | "game_script";

export type AdaptationScale = "faithful" | "balanced" | "bold";

export type StyleFocus =
  | "psychological"
  | "action"
  | "dialogue"
  | "suspense"
  | "relationship"
  | "custom";

export type AuthorControls = {
  format_type: ScriptFormat;
  adaptation_scale: AdaptationScale;
  style_focus: StyleFocus;
  preserve_items: string[];
  forbidden_changes: string[];
  author_notes?: string | null;
};

export type LlmStatus = {
  mode: "mock" | "real";
  use_mock_llm: boolean;
  api_key_configured: boolean;
  base_url_configured: boolean;
  model: string;
};

export type LlmTestResult = LlmStatus & {
  success: boolean;
  message: string;
};

export type ChapterCard = {
  chapter_id: string;
  chapter_index: number;
  title: string;
  char_count: number;
  summary: string;
  key_events: string[];
  characters: string[];
  locations: string[];
  conflicts: string[];
  emotional_beats: string[];
  clues: string[];
  adaptation_opportunities: string[];
  continuity_notes: string[];
};

export type ChapterReview = {
  chapter_id: string;
  status: "pending" | "reading" | "ready" | "approved" | "regenerating" | "failed";
  approved_at?: string | null;
  error?: string | null;
  revision_count: number;
};

export type ChapterReviewItem = {
  chapter: {
    index: number;
    title: string;
    text: string;
    char_count: number;
  };
  card: ChapterCard | null;
  review: ChapterReview;
};

export type ChapterReviewsResponse = {
  run_id: string;
  items: ChapterReviewItem[];
};

export type ChapterChatMessage = {
  id: string;
  chapter_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export type ChapterChatMessagesResponse = {
  messages: ChapterChatMessage[];
};

export async function createRun(text: string, file?: File | null): Promise<RunInfo> {
  const form = new FormData();
  if (file) {
    form.append("file", file);
  } else {
    form.append("text", text);
  }
  const response = await fetch(`${API_BASE_URL}/api/runs`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const result = await response.json();
  return getRun(result.run_id);
}

export async function listRuns(): Promise<RunListItem[]> {
  const response = await fetch(`${API_BASE_URL}/api/runs`);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const result = await response.json();
  return result.runs;
}

export async function intakeRun(text: string, file?: File | null): Promise<RunInfo> {
  const form = new FormData();
  if (file) {
    form.append("file", file);
  } else {
    form.append("text", text);
  }
  const response = await fetch(`${API_BASE_URL}/api/runs/intake`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const result = await response.json();
  return getRun(result.run_id);
}

export async function generateRun(
  runId: string,
  controls: AuthorControls,
): Promise<RunInfo> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ controls }),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const result = await response.json();
  return getRun(result.run_id);
}

export async function buildPlan(runId: string): Promise<RunInfo> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/build-plan`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const result = await response.json();
  return getRun(result.run_id);
}

export async function getChapterReviews(runId: string): Promise<ChapterReviewsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/chapter-reviews`);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.json();
}

export async function approveChapter(runId: string, chapterId: string): Promise<ChapterReviewsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/chapter-cards/${chapterId}/approve`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.json();
}

export async function approveAllChapters(runId: string): Promise<ChapterReviewsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/chapter-cards/approve-all`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.json();
}

export async function regenerateChapter(runId: string, chapterId: string): Promise<ChapterReviewsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/chapter-cards/${chapterId}/regenerate`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.json();
}

export async function getChapterChatMessages(
  runId: string,
  chapterId: string,
): Promise<ChapterChatMessagesResponse> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/chapter-cards/${chapterId}/chat/messages`);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.json();
}

export async function getRun(runId: string): Promise<RunInfo> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}`);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.json();
}

export async function getArtifact(runId: string, name: string): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/artifacts/${name}`);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.text();
}

export function artifactUrl(runId: string, name: string): string {
  return `${API_BASE_URL}/api/runs/${runId}/artifacts/${name}`;
}

export async function getScriptSchema(): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE_URL}/api/schema/script`);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.json();
}

export async function validateYaml(
  runId: string,
  yamlText: string,
): Promise<ValidationReport> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/validate-yaml`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ yaml_text: yamlText }),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const result = await response.json();
  return result.report;
}

export async function getLlmStatus(): Promise<LlmStatus> {
  const response = await fetch(`${API_BASE_URL}/api/llm/status`);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.json();
}

export async function testLlmConnection(): Promise<LlmTestResult> {
  const response = await fetch(`${API_BASE_URL}/api/llm/test`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.json();
}

async function errorText(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    return payload.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}
