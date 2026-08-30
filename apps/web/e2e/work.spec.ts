import { expect, test } from "@playwright/test";

test.describe("work mode", () => {
  test("work run plans and produces a reply", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /^(Work|工作)$/ }).click();
    await expect(page.getByText(/What would you like to work on|你想完成什么工作/)).toBeVisible();

    const box = page.locator("textarea").first();
    await box.fill("Do a small calculation");
    await box.press("Enter");

    // Mode is chosen only while creating the conversation, matching ChatGPT.
    await expect(page.getByRole("button", { name: /^(Work|工作)$/ })).toHaveCount(0);

    // The work run should produce a streamed reply (mock model).
    await expect(page.getByText("streamed mock reply", { exact: false }).first()).toBeVisible({ timeout: 45000 });
  });
});
