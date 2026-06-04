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

async function errorText(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    return payload.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}
