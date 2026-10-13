import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const command = process.argv[2];
const forwarded = process.argv.slice(3);
const option = (name, fallback) => {
  const index = forwarded.indexOf(name);
  return index === -1 ? fallback : forwarded[index + 1];
};
const uv = (args) => {
  const result = spawnSync(
    "uv",
    ["run", "--locked", "--directory", "apps/api", ...args],
    {
      cwd: root,
      stdio: "inherit",
      windowsHide: true,
      env: {
        ...process.env,
        UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? root + ".cache/uv",
        PYTHONPATH: root + "apps/api/src",
      },
    },
  );
  if (result.error) console.error(result.error.message);
  if (result.status !== 0) process.exit(result.status ?? 1);
};
if (command === "dev") {
  const port = option("--port", process.env.VETOQ_API_PORT ?? "18000");
  if (!port || !/^\d{1,5}$/.test(port) || Number(port) > 65535) {
    console.error("VETOQ API port must be an integer from 1 to 65535.");
    process.exit(1);
  }
  uv([
    "uvicorn",
    "vetoq.main:create_app",
    "--factory",
    "--app-dir",
    "src",
    "--host",
    "127.0.0.1",
    "--port",
    port,
    "--reload",
    "--reload-dir",
    "src",
  ]);
} else if (command === "verify") {
  uv(["ruff", "check", "."]);
  uv(["ruff", "format", "--check", "."]);
  uv(["mypy"]);
  uv(["pytest"]);
} else if (command === "migrate") {
  uv(["alembic", "upgrade", "head"]);
} else if (command === "worker") {
  uv(["python", "-m", "vetoq.cli", "run-worker", ...forwarded]);
} else if (command === "provision") {
  uv(["python", "-m", "vetoq.cli", "provision", ...forwarded]);
} else if (command === "retain") {
  uv(["python", "-m", "vetoq.cli", "retain"]);
} else if (command === "live-groq") {
  uv(["python", "tests/live_groq_smoke.py"]);
} else {
  console.error(
    "Usage: node scripts/api.mjs dev|verify|migrate|worker|provision|retain|live-groq",
  );
  process.exitCode = 1;
}
