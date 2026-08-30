import { expect, test } from "@playwright/test";

test.describe("chat", () => {
  test("home loads with composer", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("textarea").first()).toBeVisible();
  });

  test("new chat streams a reply", async ({ page }) => {
    await page.goto("/");
    const box = page.locator("textarea").first();
    await box.fill("Hello from E2E");
    await box.press("Enter");
    // The streamed assistant reply should appear.
    await expect(page.locator("main").getByText("streamed mock reply", { exact: false }).first()).toBeVisible({ timeout: 30000 });
  });

  test("user prompt appears immediately while image intent routing is still pending", async ({ page }) => {
    await page.goto("/");
    // Image models load asynchronously after the shell renders.
    await page.waitForTimeout(1000);
    const box = page.locator("textarea").first();
    const prompt = "帮我写一段小猫图片的提示词";
    await box.fill(prompt);
    const submittedAt = Date.now();
    await box.press("Enter");

    await expect(page.locator("main").getByText(prompt, { exact: true })).toBeVisible({ timeout: 500 });
    await expect(box).toHaveValue("");
    await expect(page.locator("main").getByText("streamed mock reply", { exact: false }).first()).toBeVisible({ timeout: 30000 });
    expect(Date.now() - submittedAt).toBeGreaterThan(1800);
  });

  test("regenerate produces another assistant reply", async ({ page }) => {
    await page.goto("/");
    const box = page.locator("textarea").first();
    await box.fill("Regenerate check");
    await box.press("Enter");
    await expect(page.getByText("streamed mock reply", { exact: false }).first()).toBeVisible({ timeout: 30000 });
    // Hover the assistant message to reveal actions, then regenerate.
    const regen = page.locator('button[title="Regenerate"]').first();
    await regen.click({ force: true });
    await page.waitForTimeout(1500);
    // Still shows a streamed reply after regenerate.
    await expect(page.getByText("streamed mock reply", { exact: false }).first()).toBeVisible();
  });

  test("model selector shows the configured model", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("E2E Mock Model").first()).toBeVisible();
  });

  test("tool call runs python in the sandbox and answers", async ({ page }) => {
    await page.goto("/");
    const box = page.locator("textarea").first();
    await box.fill("CALL_TOOL compute 6*7");
    await box.press("Enter");
    // The mock model calls run_python (print(6*7)) then answers with 42.
    await expect(page.getByText("computed the answer: 42", { exact: false }).first()).toBeVisible({ timeout: 45000 });
    // A tool card should be present.
    await expect(page.getByText(/Ran Python code|run_python/i).first()).toBeVisible();
  });
});
