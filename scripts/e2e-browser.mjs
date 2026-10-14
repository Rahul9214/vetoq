import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const apiPort = "18010";

function fileValues(path) {
  const values = {};
  let text = "";
  try {
    text = readFileSync(path, "utf8").replace(/^\uFEFF/, "");
  } catch {
    return values;
  }
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const index = trimmed.indexOf("=");
    const key = trimmed.slice(0, index).trim();
    let value = trimmed.slice(index + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

function databaseName(url) {
  try {
    return decodeURIComponent(new URL(url).pathname.replace(/^\/+/, ""));
  } catch {
    return "";
  }
}

const fileEnv = fileValues(`${root}.env`);
const testUrl =
  process.env.VETOQ_TEST_DATABASE_URL || fileEnv.VETOQ_TEST_DATABASE_URL;
const developmentUrl =
  process.env.VETOQ_DATABASE_URL || fileEnv.VETOQ_DATABASE_URL;
const testName = testUrl ? databaseName(testUrl) : "";
const developmentName = developmentUrl ? databaseName(developmentUrl) : "";

if (!testUrl || !testName.endsWith("_test") || testName === "_test") {
  console.error(
    "Browser E2E requires VETOQ_TEST_DATABASE_URL whose database name ends with _test.",
  );
  process.exit(1);
}
if (developmentName && developmentName === testName) {
  console.error(
    "Browser E2E database must differ from the development database.",
  );
  process.exit(1);
}

const children = [];
let stopping = false;

function start(command, args, extraEnv, cwd) {
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, ...extraEnv },
    stdio: "inherit",
    windowsHide: true,
    shell: process.platform === "win32" && command === "pnpm",
  });
  children.push(child);
  return child;
}

function shutdown(code) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (!child.pid || child.killed) continue;
    if (process.platform === "win32") {
      spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
        windowsHide: true,
        stdio: "ignore",
      });
    } else {
      child.kill("SIGTERM");
    }
  }
  setTimeout(() => process.exit(code), 400);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

const apiEnv = {
  VETOQ_DATABASE_URL: testUrl,
  VETOQ_ENVIRONMENT: "development",
  PYTHONPATH: `${root}apps${sep}api${sep}src`,
};

const api = start(
  "uv",
  [
    "run",
    "--locked",
    "--directory",
    "apps/api",
    "uvicorn",
    "vetoq.main:create_app",
    "--factory",
    "--app-dir",
    "src",
    "--host",
    "127.0.0.1",
    "--port",
    apiPort,
  ],
  apiEnv,
  root,
);

start(
  "uv",
  [
    "run",
    "--locked",
    "--directory",
    "apps/api",
    "python",
    "-m",
    "vetoq.cli",
    "run-worker",
  ],
  apiEnv,
  root,
);

const deadline = Date.now() + 60_000;
let ready = false;
while (Date.now() < deadline) {
  if (api.exitCode !== null) {
    console.error("Browser E2E API exited before it was ready.");
    shutdown(1);
    break;
  }
  try {
    const response = await fetch(`http://127.0.0.1:${apiPort}/health/ready`);
    if (response.ok) {
      ready = true;
      break;
    }
  } catch {
    // The API process is still starting.
  }
  await new Promise((resolve) => setTimeout(resolve, 500));
}
if (!ready) {
  console.error("Browser E2E API was not ready.");
  shutdown(1);
} else {
  const web = start(
    "pnpm",
    ["start", "--port", "3000"],
    { VETOQ_API_URL: `http://127.0.0.1:${apiPort}` },
    `${root}apps/web`,
  );
  web.on("exit", (code) => shutdown(code ?? 0));
}
