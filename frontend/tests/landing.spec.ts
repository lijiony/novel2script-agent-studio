import { expect, test } from "@playwright/test";

test("landing page explains the adaptation journey and links to workbench", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("AI 改编副编剧工作台")).toBeVisible();
  await expect(page.getByRole("heading", { name: "把长篇小说改成可继续打磨的剧本初稿" })).toBeVisible();
  await expect(page.locator("#journey").getByText("改编旅程", { exact: true })).toBeVisible();
  await expect(page.getByText("不是黑箱生成", { exact: true })).toBeVisible();
  await expect(page.getByText("可审计、可塑形")).toBeVisible();
  await expect(page.getByText("为什么用结构化 Schema")).toBeVisible();
  await expect(page.getByText("YAML 剧本初稿")).toBeVisible();

  await page.getByRole("link", { name: "开始改编" }).click();
  await expect(page).toHaveURL(/\/workbench$/);
});
