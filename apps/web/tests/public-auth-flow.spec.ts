import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const appOrigin = "http://localhost:3000";

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

async function signInWithTicket(page: Page, ticket: string) {
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
}

test.use({
  baseURL: appOrigin,
  storageState: { cookies: [], origins: [] },
});

test("public page leads through sign-in to the workbench", async ({ page }) => {
  await page.goto(appOrigin);
  await expect(
    page.getByRole("heading", { name: /Give AI room to work/i }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Guarded execution workspace" }),
  ).toHaveCount(0);
  await page
    .getByRole("link", { name: "Open secure workbench" })
    .first()
    .click();
  await expect(page).toHaveURL(/\/sign-in/);
  await expect(
    page.getByRole("heading", { name: "Define the authority." }),
  ).toBeVisible();
  await expect(page.locator(".vetoq-clerk-root")).toBeVisible({
    timeout: 15_000,
  });
  await signInWithTicket(page, await clerkSignInToken());
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
  await expect(
    page.getByRole("heading", { name: "Guarded execution workspace" }),
  ).toBeVisible({ timeout: 20_000 });
  await expect(
    page.getByRole("heading", { name: /Give AI room to work/i }),
  ).toHaveCount(0);
});
