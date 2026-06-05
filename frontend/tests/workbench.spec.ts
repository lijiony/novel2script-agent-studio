import { expect, test } from "@playwright/test";

const sixChapterNovel = Array.from({ length: 6 }, (_, index) => {
  const chapter = index + 1;
  return `第${chapter}章 线索${chapter}

林夏在第${chapter}个地点发现父亲留下的线索。周砚提醒她不要只看表面的谜题，
因为旧剧院的灯光、门票和钟楼时间都互相呼应。林夏决定继续追查，
但她也开始怀疑父亲当年失踪并不是意外。`;
}).join("\n\n");

test("reviews chapters before planning and keeps artifacts hidden until script generation", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: /把小说改成/ })).toBeVisible();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);
  await page.getByRole("button", { name: "模型设置" }).click();
  await expect(page.getByText("API Key 请填入")).toBeVisible();
  await expect(page.getByText("Mock Demo")).toBeVisible();
  await page.getByRole("button", { name: "关闭" }).click();

  await page.getByPlaceholder("粘贴至少三章小说文本...").fill(sixChapterNovel);
  await page.getByRole("button", { name: "开始分析" }).click();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);

  await expect(page.getByText("章节理解确认")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".review-card")).toHaveCount(5);
  await expect(page.getByText("第 6 章")).toHaveCount(0);
  await page.getByRole("button", { name: "展开全部" }).click();
  await expect(page.locator(".review-card")).toHaveCount(6);
  await expect(page.getByText("第 6 章")).toBeVisible();

  await page.locator(".review-card").first().getByRole("button", { name: "重新理解" }).click();
  await expect(page.locator(".review-card").first().getByText("重读 1")).toBeVisible({ timeout: 45_000 });
  await page.locator(".review-card").first().getByRole("button", { name: "讨论/修改理解" }).click();
  await expect(page.getByTestId("chapter-chat-panel")).toBeVisible();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);
  await page.getByPlaceholder(/指出你不满意的地方/).fill("这一章父亲留下线索的动机要更明确。");
  await page.getByTestId("chapter-chat-panel").getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("思考摘要")).toBeVisible();
  await expect(page.getByText("重新理解本章")).toBeVisible();
  await page.getByTestId("chapter-chat-panel").getByRole("button", { name: "关闭" }).click();

  await page.getByRole("button", { name: "全部通过" }).click();
  await expect(page.getByText("所有章节已通过")).toBeVisible();
  await page.getByRole("button", { name: "生成 Story Bible 和改编计划" }).click();

  await expect(page.getByText("副编剧建议")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("全书主线")).toBeVisible();
  await expect(page.getByText("为什么推荐这个方向")).toBeVisible();
  await expect(page.getByText("分章改编理由")).toBeVisible();
  await expect(page.getByRole("button", { name: "采纳计划并生成剧本" })).toBeVisible();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);

  await page.getByLabel("剧本类型").selectOption("short_drama");
  await page.getByLabel("改编尺度").selectOption("faithful");
  await page.getByLabel("风格偏向").selectOption("psychological");
  await page.getByLabel("作者备注").fill("心理活动要转成可表演动作。");
  await page.getByRole("button", { name: "采纳计划并生成剧本" }).click();

  await expect(page.getByText("剧本已生成")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByTestId("artifact-panel")).toBeVisible();
  await expect(page.getByText("重新校验 YAML")).toBeVisible();

  await page.getByRole("button", { name: "重新校验 YAML" }).click();
  await expect(page.getByText("校验通过")).toBeVisible();

  await page.getByRole("button", { name: "关闭产物面板" }).click();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);

  await page.locator(".sidebar-actions").getByRole("button", { name: "下载产物" }).click();
  await expect(page.getByText("下载 script.yaml")).toBeVisible();
  await expect(page.getByText("下载 adaptation_plan.json")).toBeVisible();
  await expect(page.getByText("下载 story_bible.json")).toBeVisible();

  await page.getByRole("button", { name: "新建改编" }).click();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);
  await expect(page.getByText("章节理解确认")).toHaveCount(0);
  await page.getByRole("button", { name: "开始分析" }).click();
  await expect(page.getByText("章节理解确认")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".task-item").nth(1)).toBeVisible();
});
