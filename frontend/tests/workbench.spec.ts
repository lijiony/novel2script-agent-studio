import { expect, test } from "@playwright/test";

test.setTimeout(240_000);

const aiTimeout = 90_000;

const sixChapterNovel = Array.from({ length: 6 }, (_, index) => {
  const chapter = index + 1;
  return `第${chapter}章 线索${chapter}

林夏在第${chapter}个地点发现父亲留下的线索。周砚提醒她不要只看表面的谜题，
因为旧剧院的灯光、门票和钟楼时间都互相呼应。林夏决定继续追查，
但她也开始怀疑父亲当年失踪并不是意外。`;
}).join("\n\n");

test("reviews chapters before planning and keeps artifacts hidden until script generation", async ({ page }) => {
  await page.goto("/workbench");

  await expect(page.getByRole("heading", { name: /把小说改成/ })).toBeVisible();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);
  await page.getByRole("button", { name: "模型设置" }).click();
  await expect(page.getByText("API Key 请填入")).toBeVisible();
  await expect(page.getByText("Mock Demo")).toBeVisible();
  await page.getByRole("button", { name: "关闭" }).click();

  await page.getByPlaceholder("粘贴至少三章小说文本...").fill(sixChapterNovel);
  await page.getByRole("button", { name: "开始分析" }).click();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);

  await expect(page.getByText("章节理解确认")).toBeVisible({ timeout: aiTimeout });
  await expect(page.locator(".review-card")).toHaveCount(5);
  await expect(page.getByText("第 6 章")).toHaveCount(0);
  await page.getByRole("button", { name: "展开全部" }).click();
  await expect(page.locator(".review-card")).toHaveCount(6);
  await expect(page.getByText("第 6 章")).toBeVisible();
  await expect(page.getByText("已读懂 6/6 章")).toBeVisible({ timeout: aiTimeout });

  await page.locator(".review-card").first().getByRole("button", { name: "讨论/修改理解" }).click();
  await expect(page.getByTestId("chapter-chat-panel")).toBeVisible();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);
  await page.getByPlaceholder(/指出你不满意的地方/).fill("这一章父亲留下线索的动机要更明确。");
  const chapterChatResponse = page.waitForResponse((response) => (
    response.url().includes("/chapter-cards/ch_001/chat/stream")
    && response.request().method() === "POST"
  ));
  await page.getByTestId("chapter-chat-panel").getByRole("button", { name: "发送" }).click();
  expect((await chapterChatResponse).ok()).toBeTruthy();
  await expect(page.getByRole("button", { name: "带着讨论重新理解" })).toBeVisible();
  await page.getByTestId("chapter-chat-panel").getByRole("button", { name: "关闭" }).click();

  await page.getByRole("button", { name: "全部通过" }).click();
  await expect(page.getByText("所有章节已通过")).toBeVisible();
  await page.getByRole("button", { name: "生成 Story Bible 和改编计划" }).click();

  await expect(page.getByText("副编剧建议")).toBeVisible({ timeout: aiTimeout });
  await expect(page.getByText("全书主线")).toBeVisible();
  await expect(page.getByText("为什么推荐这个方向")).toBeVisible();
  await expect(page.getByText("分章改编理由")).toBeVisible();
  await expect(page.getByRole("button", { name: "生成每章剧本卡" })).toBeVisible();
  await expect(page.getByTestId("artifact-panel")).toHaveCount(0);

  await page.getByLabel("剧本类型").selectOption("short_drama");
  await page.getByLabel("改编尺度").selectOption("faithful");
  await page.getByLabel("风格偏向").selectOption("psychological");
  await page.getByLabel("作者备注").fill("心理活动要转成可表演动作。");
  const scopeCard = page.locator(".generation-scope-card");
  await scopeCard.getByRole("button", { name: "前 3 章" }).click();
  await expect(scopeCard.getByText("已选择第 1, 2, 3 章")).toBeVisible();
  await scopeCard.getByRole("button", { name: /第 2 章/ }).click();
  await scopeCard.getByRole("button", { name: /第 5 章/ }).click();
  await expect(scopeCard.getByText("已选择第 1, 3, 5 章")).toBeVisible();
  await page.getByRole("button", { name: "生成每章剧本卡" }).click();

  await expect(page.getByText("章节剧本卡确认")).toBeVisible({ timeout: aiTimeout });
  const scriptGrid = page.getByTestId("chapter-script-review-grid");
  await expect(scriptGrid.locator(".review-card")).toHaveCount(3);
  await expect(scriptGrid.getByText("第 1 章剧本卡")).toBeVisible();
  await expect(scriptGrid.getByText("第 3 章剧本卡")).toBeVisible();
  await expect(scriptGrid.getByText("第 5 章剧本卡")).toBeVisible();
  await expect(scriptGrid.getByText("第 2 章剧本卡")).toHaveCount(0);
  await page.getByTestId("chapter-script-review-grid").locator(".review-card").first().getByRole("button", { name: "讨论/修改剧本" }).click();
  await expect(page.getByTestId("chapter-chat-panel")).toBeVisible();
  await expect(page.getByTestId("chapter-chat-panel").getByText("剧本卡讨论")).toBeVisible();
  await page.getByTestId("chapter-chat-panel").getByPlaceholder(/指出你不满意的地方/).fill("这一章开场不够紧张，要带着这个意见重写。");
  const scriptChatResponse = page.waitForResponse((response) => (
    response.url().includes("/chapter-script-cards/ch_001/chat/stream")
    && response.request().method() === "POST"
  ));
  await page.getByTestId("chapter-chat-panel").getByRole("button", { name: "发送" }).click();
  expect((await scriptChatResponse).ok()).toBeTruthy();
  await expect(page.getByRole("button", { name: "带着讨论重写本章剧本卡" })).toBeVisible();
  const regenerateScriptResponse = page.waitForResponse((response) => (
    response.url().includes("/chapter-script-cards/ch_001/regenerate")
    && response.request().method() === "POST"
  ));
  await page.getByTestId("chapter-chat-panel").getByRole("button", { name: "带着讨论重写本章剧本卡" }).click();
  await expect(page.getByTestId("chapter-chat-panel").getByRole("button", { name: "重写中..." })).toBeVisible();
  expect((await regenerateScriptResponse).ok()).toBeTruthy();
  await expect(scriptGrid.getByText("已重写，待确认")).toBeVisible({ timeout: aiTimeout });
  await page.getByTestId("chapter-chat-panel").getByRole("button", { name: "关闭" }).click();
  await page.locator(".script-workbench").getByRole("button", { name: "全部通过" }).click();
  await expect(page.getByText("所有章节剧本卡已通过")).toBeVisible();
  await page.locator(".script-workbench").getByRole("button", { name: "连贯性合成并导出 YAML" }).click();

  await expect(page.getByText("剧本已生成")).toBeVisible({ timeout: aiTimeout });
  await expect(page.getByTestId("artifact-panel")).toBeVisible();
  await expect(page.getByText("重新校验 YAML")).toBeVisible();
  await expect(page.getByTestId("artifact-panel").getByText("最终确认")).toBeVisible();
  await page.getByRole("button", { name: "剧本不满意" }).click();
  await expect(page.getByRole("button", { name: "章节和连贯性都不满意" })).toBeVisible();
  await page.getByRole("button", { name: "某个剧本点不满意" }).click();
  await page.getByPlaceholder(/说明哪里不满意/).fill("第三章对白太解释，需要先跟我确认再重写。");
  await page.getByPlaceholder(/希望怎么改/).fill("减少解释，加强动作和停顿。");
  const applyFeedbackResponse = page.waitForResponse((response) => (
    response.url().includes("/final-feedback/")
    && response.url().includes("/apply")
    && response.request().method() === "POST"
  ));
  await page.getByRole("button", { name: "发送给 AI 诊断" }).click();
  await expect(page.getByText("我判断这更像具体剧本点问题")).toBeVisible({ timeout: aiTimeout });
  expect((await applyFeedbackResponse).ok()).toBeTruthy();
  await expect(page.getByText("已开始重写目标章节剧本卡")).toBeVisible({ timeout: aiTimeout });
  await expect(page.getByText("剧本已生成")).toBeVisible({ timeout: aiTimeout });
  await expect(page.getByTestId("artifact-panel")).toBeVisible();

  await page.getByRole("button", { name: "重新校验 YAML" }).click();
  await expect(page.getByText("校验通过")).toBeVisible();
  await page.getByTestId("artifact-panel").getByRole("button", { name: "YAML" }).click();
  const confirmResponsePromise = page.waitForResponse((response) => (
    response.url().includes("/final-confirm")
    && response.request().method() === "POST"
  ));
  await page.getByTestId("artifact-panel").getByRole("button", { name: "确认剧本" }).click();
  expect((await confirmResponsePromise).ok()).toBeTruthy();

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
  await expect(page.getByText("章节理解确认")).toBeVisible({ timeout: aiTimeout });
  await expect(page.locator(".task-item").nth(1)).toBeVisible();
});
