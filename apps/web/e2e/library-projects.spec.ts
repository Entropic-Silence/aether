import { expect, test } from "@playwright/test";

test.describe("library & projects", () => {
  test("library page loads", async ({ page }) => {
    await page.goto("/library");
    await expect(page.getByText("Library").first()).toBeVisible();
  });

  test("projects page lists and can create a project", async ({ page }) => {
    await page.goto("/projects");
    await expect(page.getByText("Projects").first()).toBeVisible();
    await page.getByRole("button", { name: /New project/i }).click();
    await page.locator('input[placeholder="Project name"]').fill("E2E Project");
    await page.getByRole("button", { name: "Create" }).click();
    await expect(page.getByText("E2E Project").first()).toBeVisible({ timeout: 10000 });
  });
});
