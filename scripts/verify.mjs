import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const pnpm = process.env.npm_execpath;
if (!pnpm) {
  console.error("Run this verification through pnpm verify.");
  process.exit(1);
}
for (const command of [
  "format:check",
  "verify:web",
  "verify:api",
  "test:browser",
]) {
  const result = spawnSync(process.execPath, [pnpm, "run", command], {
    cwd: root,
    stdio: "inherit",
    windowsHide: true,
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
  });
  if (result.error) console.error(result.error.message);
  if (result.status !== 0) process.exit(result.status ?? 1);
}
