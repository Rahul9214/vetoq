import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const pnpm = process.env.npm_execpath;
if (!pnpm) {
  console.error("Run through pnpm browsers:install.");
  process.exit(1);
}
const result = spawnSync(
  process.execPath,
  [
    pnpm,
    "--filter",
    "@vetoq/web",
    "exec",
    "playwright",
    "install",
    "chromium",
    "firefox",
    "webkit",
  ],
  {
    cwd: root,
    stdio: "inherit",
    windowsHide: true,
    env: {
      ...process.env,
      PLAYWRIGHT_BROWSERS_PATH:
        process.env.PLAYWRIGHT_BROWSERS_PATH ?? root + ".cache/ms-playwright",
    },
  },
);
if (result.error) console.error(result.error.message);
process.exitCode = result.status ?? 1;
