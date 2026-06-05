import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const pidFile = path.resolve("test-results", "server-pids.json");

type StartedServer = {
  name: string;
  pid: number;
};

async function globalSetup() {
  const started: StartedServer[] = [];
  if (!(await isReachable("http://127.0.0.1:8000/health"))) {
    const backend = spawn("node", ["scripts/start-backend.mjs"], {
      cwd: process.cwd(),
      env: { ...process.env, USE_MOCK_LLM: "true" },
      stdio: "inherit",
    });
    if (backend.pid) {
      started.push({ name: "backend", pid: backend.pid });
    }
    await waitForUrl("http://127.0.0.1:8000/health", 30_000);
  }

  if (!(await isReachable("http://127.0.0.1:3000"))) {
    const frontend = spawn("node", ["scripts/start-frontend.mjs"], {
      cwd: process.cwd(),
      env: process.env,
      stdio: "inherit",
    });
    if (frontend.pid) {
      started.push({ name: "frontend", pid: frontend.pid });
    }
    await waitForUrl("http://127.0.0.1:3000", 60_000);
  }

  await mkdir(path.dirname(pidFile), { recursive: true });
  await writeFile(pidFile, JSON.stringify(started, null, 2), "utf-8");
}

async function waitForUrl(url: string, timeoutMs: number) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await isReachable(url)) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function isReachable(url: string) {
  try {
    const response = await fetch(url);
    return response.ok;
  } catch {
    return false;
  }
}

export default globalSetup;
