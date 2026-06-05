import { readFile, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";

const pidFile = path.resolve("test-results", "server-pids.json");

async function globalTeardown() {
  let servers: Array<{ name: string; pid: number }> = [];
  try {
    servers = JSON.parse(await readFile(pidFile, "utf-8"));
  } catch {
    servers = [];
  }

  for (const server of servers) {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(server.pid), "/t", "/f"], { stdio: "ignore" });
    } else {
      try {
        process.kill(server.pid, "SIGTERM");
      } catch {
        // Server already exited.
      }
    }
  }

  await rm(pidFile, { force: true });
}

export default globalTeardown;
