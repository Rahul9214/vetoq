import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

for (const width of [320, 360, 390, 430, 768, 1024, 1280, 1440, 1920]) {
  test(
    "product shell reflows at " + width + "px",
    async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await expect(
        page.getByRole("heading", {
          level: 1,
          name: /Give AI room to work/i,
        }),
      ).toBeVisible({ timeout: 20_000 });
      await expect(
        page.getByRole("heading", {
          level: 2,
          name: "Credentials do not answer whether this action was delegated.",
        }),
      ).toBeVisible();
      await expect(page.getByRole("banner")).toBeVisible();
      const dimensions = await page.evaluate(() => ({
        document: document.documentElement.scrollWidth,
        viewport: document.documentElement.clientWidth,
      }));
      expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
      await expect(page.getByRole("contentinfo")).toBeVisible();
      if (width === 390 || width === 1440)
        await page.screenshot({
          path: testInfo.outputPath("shell.png"),
          fullPage: true,
        });
    },
  );
}
test("configured Clerk reaches a usable signed-out state", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Sign in" }).first()).toBeVisible(
    {
      timeout: 15_000,
    },
  );
  await expect(
    page.getByRole("link", { name: "Open secure workbench" }).first(),
  ).toBeVisible();
});
test("keyboard skip link moves focus to main", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to main content" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
});
test("has no automated WCAG A/AA violations at compact and wide sizes", async ({
  page,
}) => {
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const report = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(report.violations).toEqual([]);
  }
});
test("supports reduced motion and 400% text enlargement at 320px", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto("/");
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "400%";
  });
  expect(
    await page.evaluate(
      () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    ),
  ).toBe(true);
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
