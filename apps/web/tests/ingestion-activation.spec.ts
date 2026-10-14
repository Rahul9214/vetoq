import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Request } from "@playwright/test";
import { readFileSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const appOrigin = "http://localhost:3000";
const storagePath = join(tmpdir(), "vetoq-h2b1-storage.json");
const goal = "Review this support note and create one ticket.";
const plainSource = "Customer cannot sign in after a password reset.";
const jsonSource = '{"ticket":"reset"}';
const brokenJson = '{"vetoq_json_marker":';
const htmlSource =
  "<p>vetoq-visible-marker</p><script>window.__vetoqExecuted=1</script>";
const allowedFields = [
  "workspace_id",
  "goal",
  "source",
  "media_type",
  "confirmed",
];
const persistedState =
  /NO ACTION|FAILED|BLOCKED|AWAITING REVIEW|COMPLETED|VERIFYING/;

function envValue(name: string): string {
  const file = fileURLToPath(new URL("../.env.local", import.meta.url));
  for (const line of readFileSync(file, "utf8")
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith(`${name}=`)) continue;
    return trimmed
      .slice(name.length + 1)
      .trim()
      .replace(/^['"]|['"]$/g, "");
  }
  throw new Error("clerk_test_secret_required");
}

async function clerkSignInToken(): Promise<string> {
  const secret = envValue("CLERK_SECRET_KEY");
  if (!secret.startsWith("sk_test_"))
    throw new Error("clerk_test_secret_required");
  const users = await fetch("https://api.clerk.com/v1/users?limit=1", {
    headers: { Authorization: `Bearer ${secret}` },
  });
  if (!users.ok) throw new Error(`clerk_users_${users.status}`);
  const listed = (await users.json()) as Array<{ id?: string }>;
  const userId = listed[0]?.id;
  if (!userId?.startsWith("user_")) throw new Error("clerk_test_user_missing");
  const created = await fetch("https://api.clerk.com/v1/sign_in_tokens", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${secret}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ user_id: userId, expires_in_seconds: 600 }),
  });
  if (!created.ok) throw new Error(`clerk_ticket_${created.status}`);
  const body = (await created.json()) as { token?: string };
  if (!body.token) throw new Error("clerk_ticket_missing");
  return body.token;
}

async function establishSession(page: Page, ticket: string) {
  await page.goto(appOrigin);
  await page.waitForFunction(
    () =>
      Boolean(
        (window as unknown as { Clerk?: { loaded?: boolean } }).Clerk?.loaded,
      ),
    undefined,
    { timeout: 30_000 },
  );
  const status = await page.evaluate(async (value: string) => {
    const clerk = (
      window as unknown as {
        Clerk: {
          user: unknown;
          signOut: () => Promise<void>;
          client: {
            signIn: {
              create: (args: {
                strategy: "ticket";
                ticket: string;
              }) => Promise<{
                status: string | null;
                createdSessionId: string | null;
              }>;
            };
          };
          setActive: (args: { session: string }) => Promise<void>;
        };
      }
    ).Clerk;
    if (clerk.user) await clerk.signOut();
    const attempt = await clerk.client.signIn.create({
      strategy: "ticket",
      ticket: value,
    });
    if (attempt.status !== "complete" || !attempt.createdSessionId) {
      return attempt.status ?? "incomplete";
    }
    await clerk.setActive({ session: attempt.createdSessionId });
    return "complete";
  }, ticket);
  expect(status).toBe("complete");
  try {
    await page.goto(appOrigin, { waitUntil: "commit" });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (
      !/NS_BINDING_ABORTED|interrupted by another navigation/i.test(message)
    ) {
      throw error;
    }
    await page.goto(appOrigin, { waitUntil: "commit" });
  }
  await expect(page.getByLabel("Declared format")).toBeVisible({
    timeout: 20_000,
  });
}

function captureSubmission(page: Page) {
  let body: Record<string, unknown> | undefined;
  const handler = (request: Request) => {
    if (
      request.method() !== "POST" ||
      !request.url().endsWith("/api/v1/runs")
    ) {
      return;
    }
    body = request.postDataJSON() as Record<string, unknown>;
  };
  page.on("request", handler);
  return {
    async stop() {
      page.off("request", handler);
      if (!body) throw new Error("submission_not_observed");
      expect(Object.keys(body).sort()).toEqual([...allowedFields].sort());
      expect(body.confirmed).toBe(true);
      expect(typeof body.workspace_id).toBe("string");
      expect(typeof body.goal).toBe("string");
      expect(typeof body.source).toBe("string");
      expect(typeof body.media_type).toBe("string");
      return body;
    },
  };
}

async function submitFormat(page: Page, mediaType: string, source: string) {
  await page.goto(appOrigin);
  await page.getByLabel("Declared format").selectOption(mediaType);
  await page.getByLabel("Authorized goal").fill(goal);
  await page.getByLabel("Untrusted business content").fill(source);
  await page
    .getByLabel(
      "I confirm this goal, this authority, and this untrusted submission.",
    )
    .check();
  const capture = captureSubmission(page);
  const observed = page.waitForRequest(
    (request) =>
      request.method() === "POST" && request.url().endsWith("/api/v1/runs"),
  );
  await page.getByRole("button", { name: /Start guarded analysis/ }).click();
  await observed;
  const body = await capture.stop();
  expect(body.media_type).toBe(mediaType);
  return body;
}

async function focusClearance(page: Page) {
  return page.evaluate(() => {
    const active = document.activeElement;
    const shell = document.querySelector(".nav-shell");
    if (!(active instanceof HTMLElement) || !(shell instanceof HTMLElement)) {
      return null;
    }
    if (shell.contains(active) || active.classList.contains("skip-link")) {
      return { kind: "chrome" };
    }
    const box = active.getBoundingClientRect();
    const header = shell.getBoundingClientRect();
    const id = active.id;
    const kind =
      id === "workspace" ||
      id === "goal" ||
      id === "media-type" ||
      id === "source"
        ? id
        : active instanceof HTMLInputElement && active.type === "checkbox"
          ? "confirm"
          : active instanceof HTMLButtonElement
            ? "submit"
            : active.classList.contains("form-error")
              ? "alert"
              : "other";
    return {
      kind,
      gap: box.top - header.bottom,
      height: box.height,
    };
  });
}

test.describe("authenticated declared-format workbench", () => {
  test.describe.configure({ mode: "serial", timeout: 120_000 });
  test.use({ baseURL: appOrigin, storageState: storagePath });

  test.afterAll(() => {
    try {
      unlinkSync(storagePath);
    } catch {
      // The session file is absent when sign-in did not complete.
    }
  });

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({
      storageState: { cookies: [], origins: [] },
    });
    const page = await context.newPage();
    await establishSession(page, await clerkSignInToken());
    await context.storageState({ path: storagePath });
    await context.close();
  });

  test("keeps keyboard focus below the sticky header", async ({ page }) => {
    const targets = [
      "workspace",
      "goal",
      "media-type",
      "source",
      "confirm",
      "submit",
    ];
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: 800 });
      await page.goto(appOrigin);
      await expect(page.locator("#workspace")).toBeVisible();
      const seen = new Set<string>();
      for (let step = 0; step < 30 && seen.size < targets.length; step += 1) {
        await page.keyboard.press("Tab");
        const clearance = await focusClearance(page);
        if (!clearance || clearance.kind === "chrome") continue;
        if (clearance.kind === "media-type") {
          await page.keyboard.press("ArrowDown");
        }
        if (clearance.kind === "confirm") {
          await page.keyboard.press("Space");
        }
        if (!targets.includes(clearance.kind)) continue;
        seen.add(clearance.kind);
        expect(
          clearance.gap,
          `${width}px ${clearance.kind}`,
        ).toBeGreaterThanOrEqual(0);
      }
      expect([...seen].sort()).toEqual([...targets].sort());

      await page.getByLabel("Declared format").selectOption("application/json");
      await page.getByLabel("Untrusted business content").fill(brokenJson);
      await page
        .getByLabel(
          "I confirm this goal, this authority, and this untrusted submission.",
        )
        .check();
      await page
        .getByRole("button", { name: /Start guarded analysis/ })
        .click();
      const alert = page.locator(".form-error");
      await expect(alert).toBeFocused();
      const alertClearance = await focusClearance(page);
      expect(alertClearance?.kind).toBe("alert");
      expect(alertClearance?.gap, `${width}px alert`).toBeGreaterThanOrEqual(0);
    }
  });

  test("reaches the format selector from the keyboard at 320px", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto(appOrigin);
    const format = page.getByLabel("Declared format");
    await expect(format).toBeVisible();
    for (const label of [
      "Plain text",
      "JSON",
      "Markdown",
      "HTML",
      "Email (RFC822)",
    ]) {
      await expect(page.getByRole("option", { name: label })).toHaveCount(1);
    }
    let reached = false;
    for (let step = 0; step < 40; step += 1) {
      await page.keyboard.press("Tab");
      if (
        (await page.evaluate(() => document.activeElement?.id)) === "media-type"
      ) {
        reached = true;
        break;
      }
    }
    expect(reached).toBe(true);
    await page.keyboard.press("ArrowDown");
    await expect(format).toHaveValue("text/plain");
    await page.keyboard.press("ArrowDown");
    await expect(format).toHaveValue("application/json");
    await page.keyboard.press("Shift+Tab");
    await expect(page.getByLabel("Authorized workspace")).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(page.getByLabel("Authorized goal")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Authorized workspace")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(format).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Untrusted business content")).toBeFocused();
    const confirmation = page.getByLabel(
      "I confirm this goal, this authority, and this untrusted submission.",
    );
    await page.keyboard.press("Tab");
    await expect(confirmation).toBeFocused();
    await page.keyboard.press("Space");
    await expect(confirmation).toBeChecked();
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("button", { name: /Start guarded analysis/ }),
    ).toBeFocused();
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test("keeps the submission controls inside the page at the release widths", async ({
    page,
  }) => {
    await page.goto(appOrigin);
    await expect(page.getByLabel("Declared format")).toBeVisible();
    const confirmation =
      "I confirm this goal, this authority, and this untrusted submission.";
    for (const width of [320, 360, 390, 430, 768, 1024, 1280, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await page.evaluate(() => window.scrollTo(0, 0));
      const overflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
      for (const label of [
        "Authorized goal",
        "Declared format",
        "Untrusted business content",
        confirmation,
      ]) {
        const control = page.getByLabel(label);
        await expect(control).toBeVisible();
        const box = await control.boundingBox();
        expect(box).not.toBeNull();
        expect(box!.x).toBeGreaterThanOrEqual(-1);
        expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
      }
      const action = page.getByRole("button", {
        name: /Start guarded analysis/,
      });
      await expect(action).toBeVisible();
      await expect(
        page.getByText("Choose a declared format to continue."),
      ).toBeVisible();
      const actionBox = await action.boundingBox();
      expect(actionBox).not.toBeNull();
      expect(actionBox!.x).toBeGreaterThanOrEqual(-1);
      expect(actionBox!.x + actionBox!.width).toBeLessThanOrEqual(width + 1);
      if (width === 390 || width === 1440) {
        if (width === 1440) await page.getByLabel("Authorized goal").focus();
        if (width === 390) await page.getByLabel("Declared format").focus();
        await page.screenshot({
          path: join(tmpdir(), `vetoq-i1-${width}.png`),
        });
        await page.locator("#source").scrollIntoViewIfNeeded();
        await page.screenshot({
          path: join(tmpdir(), `vetoq-i1-${width}-content.png`),
        });
      }
    }
  });

  test("submits plain text through the BFF and polls the persisted run", async ({
    page,
  }) => {
    await submitFormat(page, "text/plain", plainSource);
    await page.waitForURL(/\/runs\/[0-9a-f-]+$/);
    await expect(page.locator(".run-hero-state")).toContainText(
      persistedState,
      { timeout: 90_000 },
    );
  });

  test("submits JSON and shows the declared type after processing", async ({
    page,
  }) => {
    await submitFormat(page, "application/json", jsonSource);
    await page.waitForURL(/\/runs\/[0-9a-f-]+$/);
    await expect(page.locator(".run-hero-state")).toContainText(
      persistedState,
      { timeout: 90_000 },
    );
    await expect(page.getByText("application/json").first()).toBeVisible();
    await expect(page.getByText("Original", { exact: true })).toBeVisible({
      timeout: 90_000,
    });
    await expect(page.getByText("Canonical text")).toBeVisible({
      timeout: 90_000,
    });
    await expect(page.getByText("JSON canonicalization").first()).toBeVisible();
    await expect(page.locator(".step-list li")).toHaveCount(1);
    await page
      .getByRole("button", { name: "View protected text" })
      .first()
      .click();
    await expect(page.locator("pre.evidence-text").first()).toContainText(
      '{"ticket":"reset"}',
    );
    expect(
      await page.evaluate(() =>
        document.querySelector(".run-narrative img, .run-narrative script"),
      ),
    ).toBeNull();
    const details = page
      .getByRole("button", { name: "Technical details" })
      .first();
    await details.focus();
    const clearance = await focusClearance(page);
    expect(clearance?.gap ?? -1).toBeGreaterThanOrEqual(0);
    await page.keyboard.press("Enter");
    await expect(details).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Enter");
    await expect(details).toHaveAttribute("aria-expanded", "false");
    for (const width of [320, 360, 390, 430, 768, 1024, 1280, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await page.evaluate(() => window.scrollTo(0, 0));
      const overflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
      if (width === 320 || width === 390) {
        await details.focus();
        const narrowClearance = await focusClearance(page);
        expect(narrowClearance?.gap ?? -1).toBeGreaterThanOrEqual(0);
      }
      if (width === 320) {
        await page.keyboard.press("Enter");
        await expect(details).toHaveAttribute("aria-expanded", "true");
        const openOverflow = await page.evaluate(
          () =>
            document.documentElement.scrollWidth -
            document.documentElement.clientWidth,
        );
        expect(openOverflow).toBeLessThanOrEqual(1);
        await page.keyboard.press("Enter");
        await expect(details).toHaveAttribute("aria-expanded", "false");
      }
      if (width === 390 || width === 1440) {
        await page.screenshot({
          path: join(tmpdir(), `vetoq-i2-run-${width}.png`),
        });
        await page.locator("#evidence-title").scrollIntoViewIfNeeded();
        await page.screenshot({
          path: join(tmpdir(), `vetoq-i2-evidence-${width}.png`),
        });
        await page.evaluate(() => window.scrollTo(0, 0));
      }
    }
  });

  test("shows a two-step email derivation on the run page", async ({
    page,
  }) => {
    const email = [
      "Content-Type: application/json; charset=utf-8",
      "",
      '{"n":1}',
      "",
    ].join("\n");
    await submitFormat(page, "message/rfc822", email);
    await page.waitForURL(/\/runs\/[0-9a-f-]+$/);
    const chain = page
      .locator(".step-list")
      .filter({ hasText: "MIME part decode" });
    await expect(chain).toBeVisible({ timeout: 90_000 });
    await expect(chain.locator("li").nth(0)).toContainText("MIME part decode");
    await expect(chain.locator("li").nth(1)).toContainText(
      "JSON canonicalization",
    );
    await expect(page.getByText("Email JSON part")).toBeVisible();
    await expect(page.getByText("Original", { exact: true })).toBeVisible();
  });

  test("shows a safe error for malformed JSON and creates no run", async ({
    page,
  }) => {
    await page.goto(appOrigin);
    await expect(page.locator("#workspace")).toBeVisible();
    const before = await page.evaluate(async () => {
      const workspace = (
        document.querySelector("#workspace") as HTMLSelectElement
      ).value;
      const response = await fetch(
        `/api/v1/runs?workspace_id=${encodeURIComponent(workspace)}`,
      );
      const body = (await response.json()) as { items?: Array<{ id: string }> };
      return (body.items ?? []).map((item) => item.id);
    });
    await page.getByLabel("Declared format").selectOption("application/json");
    await page.getByLabel("Authorized goal").fill(goal);
    await page.getByLabel("Untrusted business content").fill(brokenJson);
    await page
      .getByLabel(
        "I confirm this goal, this authority, and this untrusted submission.",
      )
      .check();
    await page.getByRole("button", { name: /Start guarded analysis/ }).click();
    const alert = page.locator(".form-error");
    await expect(alert).toContainText("malformed_content");
    await expect(alert).toContainText(
      "This content does not match the declared format.",
    );
    await expect(alert).not.toContainText("vetoq_json_marker");
    await expect(page.getByLabel("Untrusted business content")).toHaveValue(
      brokenJson,
    );
    await page.setViewportSize({ width: 1440, height: 900 });
    await alert.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: join(tmpdir(), "vetoq-i1-error-1440.png"),
    });
    await expect(page).toHaveURL(appOrigin + "/");
    await expect(page.getByLabel("Declared format")).toHaveValue(
      "application/json",
    );
    await expect(page.locator("form")).toBeVisible();
    const after = await page.evaluate(async () => {
      const workspace = (
        document.querySelector("#workspace") as HTMLSelectElement
      ).value;
      const response = await fetch(
        `/api/v1/runs?workspace_id=${encodeURIComponent(workspace)}`,
      );
      const body = (await response.json()) as { items?: Array<{ id: string }> };
      return (body.items ?? []).map((item) => item.id);
    });
    expect(after).toEqual(before);
  });

  test("renders submitted HTML as inert text", async ({ page }) => {
    let executed = false;
    page.on("dialog", () => {
      executed = true;
    });
    await submitFormat(page, "text/html", htmlSource);
    await page.waitForURL(/\/runs\/[0-9a-f-]+$/);
    await page
      .getByRole("button", { name: "View protected text" })
      .first()
      .click();
    const evidence = page.locator("pre.evidence-text").first();
    await expect(evidence).toContainText("vetoq-visible-marker");
    await expect(evidence).toContainText("window.__vetoqExecuted");
    expect(executed).toBe(false);
    expect(
      await page.evaluate(
        () =>
          (window as unknown as { __vetoqExecuted?: number }).__vetoqExecuted,
      ),
    ).toBeUndefined();
  });

  test("workbench and run narrative have no automated WCAG A/AA violations", async ({
    page,
  }) => {
    test.slow();
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(appOrigin);
      await expect(
        page.getByRole("heading", { name: "Guarded execution workspace" }),
      ).toBeVisible();
      const workbench = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(workbench.violations).toEqual([]);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await submitFormat(page, "text/plain", plainSource);
    await page.waitForURL(/\/runs\/[0-9a-f-]+$/);
    await expect(page.locator(".run-hero-state")).toBeVisible();
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      const narrative = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(narrative.violations).toEqual([]);
    }
  });
});
