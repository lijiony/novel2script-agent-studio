import { expect, test } from "@playwright/test";

test("plans adaptation before generating editable YAML", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Novel2Script Agent Studio" })).toBeVisible();
  await page.getByRole("button", { name: "分析小说" }).click();

  await expect(page.getByText("状态：planned")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".plan-report")).toContainText("Recommended format");
  await page.getByLabel("剧本类型").selectOption("short_drama");
  await page.getByLabel("改编尺度").selectOption("faithful");
  await page.getByLabel("风格偏向").selectOption("psychological");
  await page.getByLabel("作者备注").fill("心理活动要转成可表演动作。");
  await page.getByRole("button", { name: "生成剧本" }).click();

  await expect(page.getByText("状态：succeeded")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("generate_report")).toBeVisible();
  await expect(page.getByText("重新校验 YAML")).toBeVisible();

  await page.getByRole("button", { name: "重新校验 YAML" }).click();
  await expect(page.getByText("校验通过")).toBeVisible();
  await expect(page.getByRole("button", { name: "下载当前 YAML" })).toBeEnabled();
  await expect(page.getByText("计划与中间产物")).toBeVisible();
  await expect(page.getByText("最终交付产物")).toBeVisible();
  await expect(page.getByText("下载 adaptation_plan.json")).toBeVisible();
  await expect(page.getByText("下载 reader_output.json")).toBeVisible();
  await expect(page.getByText("下载 planner_output.json")).toBeVisible();
  await expect(page.getByText("下载 script.yaml")).toBeVisible();
});
