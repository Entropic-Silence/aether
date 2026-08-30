import { expect, test } from "@playwright/test";

test.describe("sharing", () => {
  test("share page renders for an unknown token", async ({ page }) => {
    await page.goto("/share/nonexistent-token-123");
    await expect(page.getByText("share isn't available", { exact: false }).first()).toBeVisible();
  });

  test("share button copies a link for a conversation", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/");
    const box = page.locator("textarea").first();
    await box.fill("Share this chat");
    await box.press("Enter");
    await expect(page.getByText("streamed mock reply", { exact: false }).first()).toBeVisible({ timeout: 30000 });
    const shareBtn = page.locator('button[title="Share conversation"]').first();
    await shareBtn.click({ force: true });
    await expect(page.getByText(/Link copied|share/i).first()).toBeVisible({ timeout: 10000 });
  });
});
