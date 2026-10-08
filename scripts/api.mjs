import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const command = process.argv[2];
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
      },
    },
  );
  if (result.error) console.error(result.error.message);
  if (result.status !== 0) process.exit(result.status ?? 1);
};
if (command === "dev") {
  uv([
    "uvicorn",
    "vetoq.main:create_app",
    "--factory",
    "--app-dir",
    "src",
    "--host",
    "127.0.0.1",
    "--port",
    "8000",
    "--reload",
  ]);
} else if (command === "verify") {
  uv(["ruff", "check", "."]);
  uv(["ruff", "format", "--check", "."]);
  uv(["mypy"]);
  uv(["pytest"]);
} else {
  console.error("Usage: node scripts/api.mjs dev|verify");
  process.exitCode = 1;
}
