import { expect, test } from "@playwright/test";

const viewports = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "narrow", width: 900, height: 900 },
  { name: "mobile", width: 390, height: 900 },
];

for (const viewport of viewports) {
  test(`landing page has no horizontal overflow on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");

    await expect(page.getByRole("link", { name: "开始改编" })).toBeVisible();
    await expect(page.getByText("AI 改编副编剧工作台")).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(2);
  });

  test(`workbench shell remains usable on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/workbench");

    await expect(page.getByTestId("workbench-shell")).toBeVisible();
    await expect(page.getByRole("button", { name: "新建改编" })).toBeVisible();
    await expect(page.getByPlaceholder("粘贴至少三章小说文本...")).toBeVisible();
    await expect(page.getByRole("button", { name: "开始分析" })).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(2);
  });
}

test("workbench context drawers open without hiding the main flow", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/workbench");

  await page.getByRole("button", { name: "模型设置" }).click();
  await expect(page.getByLabel("模型设置")).toBeVisible();
  await expect(page.getByPlaceholder("粘贴至少三章小说文本...")).toBeVisible();
  await page.getByRole("button", { name: "关闭" }).click();
  await expect(page.getByLabel("模型设置")).toHaveCount(0);
});
