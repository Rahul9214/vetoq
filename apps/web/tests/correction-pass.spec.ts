import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const widths = [320, 360, 390, 430, 768, 1024, 1280, 1440, 1920];
const sectionIds = [
  "execution-boundary",
  "method",
  "goal-lock",
  "action-guard",
  "states",
  "principles",
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
      page.getByRole("heading", { level: 1, name: /Trust the goal/i }),
    ).toBeVisible();
    for (const id of sectionIds)
      await expect(page.locator(`#${id}`)).toBeVisible();
    await expect(page.getByRole("contentinfo")).toBeVisible();
    await expectNoPageOverflow(page);

    await page.goto("/sign-in");
    await expect(
      page.getByRole("heading", {
        name: "Continue with your verified identity.",
      }),
    ).toBeVisible();
    await expect(page.getByRole("region", { name: "Sign in" })).toBeVisible();
    await expect(page.locator(".vetoq-clerk-root")).toBeVisible({
      timeout: 15_000,
    });
    await expectNoPageOverflow(page);

    await page.goto("/sign-up");
    await expect(
      page.getByRole("heading", {
        name: "Create your secure workbench access.",
      }),
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

test("public experience names every official attack family", async ({
  page,
}) => {
  await page.goto("/");
  for (const family of [
    "Instruction Override",
    "Role Change",
    "Secret Extraction",
    "Tool Abuse",
    "Credential Theft",
    "Context Poisoning",
    "Multi-Step Jailbreaks",
    "Encoded Instructions",
    "Indirect Prompt Injection",
  ]) {
    await expect(page.getByText(family, { exact: true })).toBeVisible();
  }
});

test("public and auth pages have no automated WCAG A/AA violations", async ({
  page,
}) => {
  test.slow();
  for (const width of [320, 1440]) {
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
    .locator(".boundary-figure")
    .evaluate((node) => getComputedStyle(node, "::after").animationDuration);
  expect(["0.01ms", "1e-05s", "0.00001s", "0s"]).toContain(duration);
});
