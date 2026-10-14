import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const widths = [320, 360, 390, 430, 768, 1024, 1280, 1440, 1920];
const sectionIds = [
  "problem",
  "changes",
  "execution-path",
  "boundary",
  "review",
  "verification",
  "enterprise",
] as const;

async function expectNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
}

for (const width of widths) {
  test(`public and auth compositions reflow at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });

    await page.goto("/");
    await expect(
      page.getByRole("heading", { level: 1, name: /Give AI room to work/i }),
    ).toBeVisible({ timeout: 20_000 });
    for (const id of sectionIds)
      await expect(page.locator(`#${id}`)).toBeVisible();
    await expect(page.getByRole("contentinfo")).toBeVisible();
    await expectNoPageOverflow(page);
    if (width === 390 || width === 1440) {
      await page.screenshot({
        path: join(tmpdir(), `vetoq-j-public-${width}.png`),
        fullPage: true,
      });
    }

    await page.goto("/sign-in");
    await expect(
      page.getByRole("heading", { name: "Define the authority." }),
    ).toBeVisible();
    await expect(page.getByRole("region", { name: "Sign in" })).toBeVisible();
    await expect(page.locator(".vetoq-clerk-root")).toBeVisible({
      timeout: 15_000,
    });
    await expectNoPageOverflow(page);
    if (width === 390 || width === 1440) {
      await page.screenshot({
        path: join(tmpdir(), `vetoq-j-auth-${width}.png`),
      });
    }

    await page.goto("/sign-up");
    await expect(
      page.getByRole("heading", { name: "Verify the action." }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Create account" }),
    ).toBeVisible();
    await expect(page.locator(".vetoq-clerk-root")).toBeVisible({
      timeout: 15_000,
    });
    await expectNoPageOverflow(page);
  });
}

test("mobile navigation is keyboard operable and restores focus", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Open navigation" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("navigation", { name: "Mobile navigation" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("navigation", { name: "Mobile navigation" }),
  ).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("keyboard reaches a Clerk field on the sign-in page", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/sign-in");
  const root = page.locator(".vetoq-clerk-root");
  await expect(root).toBeVisible({ timeout: 15_000 });
  let inside = false;
  for (let step = 0; step < 20; step += 1) {
    await page.keyboard.press("Tab");
    inside = await page.evaluate(() => {
      const clerk = document.querySelector(".vetoq-clerk-root");
      const active = document.activeElement;
      return Boolean(
        clerk && active instanceof HTMLElement && clerk.contains(active),
      );
    });
    if (inside) break;
  }
  expect(inside).toBe(true);
  await expectNoPageOverflow(page);
});

test("public close sits above the footer without unsupported claims", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Give AI room to work/i }),
  ).toBeVisible();
  const order = await page.evaluate(() => {
    const hero = document.querySelector(".public-hero");
    const close = document.querySelector(".public-close");
    const footer = document.querySelector(".public-footer");
    if (!hero || !close || !footer) return "missing";
    return hero.compareDocumentPosition(close) &
      Node.DOCUMENT_POSITION_FOLLOWING &&
      close.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING
      ? "ordered"
      : "misordered";
  });
  expect(order).toBe("ordered");
  await expect(
    page.getByRole("link", { name: "See VETOQ in action" }),
  ).toBeVisible();
  const text = await page.locator("body").innerText();
  expect(text.toLowerCase()).not.toContain("multimodal");
  expect(text.toLowerCase()).not.toContain("multi-agent");
  expect(text.toLowerCase()).not.toContain("hackathon");
});

test("public and auth pages have no automated WCAG A/AA violations", async ({
  page,
}) => {
  test.slow();
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of ["/", "/sign-in", "/sign-up"]) {
      await page.goto(path);
      if (path !== "/") {
        await expect(page.locator(".vetoq-clerk-root")).toBeVisible({
          timeout: 15_000,
        });
      }
      const builder = new AxeBuilder({ page }).withTags([
        "wcag2a",
        "wcag2aa",
        "wcag21aa",
        "wcag22aa",
      ]);
      if (path !== "/") {
        builder.exclude(".vetoq-clerk-root");
      }
      const report = await builder.analyze();
      expect(report.violations).toEqual([]);
    }
  }
});

test("reduced motion makes the causal boundary transition effectively static", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const duration = await page
    .locator(".path-cursor")
    .evaluate((node) => getComputedStyle(node).animationDuration);
  expect(["0.01ms", "1e-05s", "0.00001s", "0s"]).toContain(duration);
});
