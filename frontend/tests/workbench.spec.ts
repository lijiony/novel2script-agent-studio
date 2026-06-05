import { expect, test } from "@playwright/test";

test("opens the artifact panel only after generation or explicit artifact actions", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: /把小说改成/ })).toBeVisible();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);
  await page.getByRole("button", { name: "模型设置" }).click();
  await expect(page.getByText("API Key 请填入")).toBeVisible();
  await expect(page.getByText("Mock Demo")).toBeVisible();
  await page.getByRole("button", { name: "关闭" }).click();

  await page.getByRole("button", { name: "开始分析" }).click();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);

  await expect(page.getByText("副编剧建议")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("全书主线")).toBeVisible();
  await expect(page.getByText("为什么推荐这个方向")).toBeVisible();
  await expect(page.getByText("分章改编理由")).toBeVisible();
  await expect(page.getByText("原文功能").first()).toBeVisible();
  await expect(page.getByText("改编处理").first()).toBeVisible();
  await expect(page.getByText("为什么这样改").first()).toBeVisible();
  await expect(page.getByText("长文本处理说明")).toBeVisible();
  await expect(page.locator(".metric-row").getByText("建议先生成", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "采纳计划并生成剧本" })).toBeVisible();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);
  await page.locator(".sidebar-actions").getByRole("button", { name: "章节理解卡" }).click();
  await expect(page.getByTestId("artifact-panel")).toBeVisible();
  await expect(page.getByText("ch_001")).toBeVisible();
  await page.getByRole("button", { name: "关闭产物面板" }).click();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);

  await page.getByLabel("剧本类型").selectOption("short_drama");
  await page.getByLabel("改编尺度").selectOption("faithful");
  await page.getByLabel("风格偏向").selectOption("psychological");
  await page.getByLabel("作者备注").fill("心理活动要转成可表演动作。");
  await page.getByRole("button", { name: "采纳计划并生成剧本" }).click();

  await expect(page.getByText("剧本已生成")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByTestId("artifact-panel")).toBeVisible();
  await expect(page.getByText("重新校验 YAML")).toBeVisible();
  await expect(page.getByRole("button", { name: "下载当前 YAML" })).toBeEnabled();

  await page.getByRole("button", { name: "重新校验 YAML" }).click();
  await expect(page.getByText("校验通过")).toBeVisible();

  await page.getByRole("button", { name: "关闭产物面板" }).click();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);

  await page.locator(".sidebar-actions").getByRole("button", { name: "查看报告" }).click();
  await expect(page.getByTestId("artifact-panel")).toBeVisible();
  await expect(page.getByTestId("artifact-panel").getByRole("button", { name: "改编报告" })).toHaveClass(/active/);

  await page.locator(".sidebar-actions").getByRole("button", { name: "下载产物" }).click();
  await expect(page.getByText("下载 script.yaml")).toBeVisible();
  await expect(page.getByText("下载 adaptation_plan.json")).toBeVisible();
  await expect(page.getByText("下载 story_bible.json")).toBeVisible();
});
