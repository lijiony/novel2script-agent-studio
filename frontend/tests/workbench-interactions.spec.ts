import { expect, test } from "@playwright/test";

test.setTimeout(180_000);

const threeChapterNovel = `第一章 雨夜
林夏在档案馆发现一封没有编号的信。

第二章 旧剧院
她在旧剧院遇到周砚，知道父亲曾留下线索。

第三章 钟楼
林夏从台词首字里找到钟楼地址，决定继续追查。`;

async function replaceNovelInput(page: import("@playwright/test").Page, text: string) {
  const input = page.getByPlaceholder("粘贴至少三章小说文本...");
  await input.evaluate((element, value) => {
    const textarea = element as HTMLTextAreaElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
    setter?.call(textarea, value);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  }, text);
  await expect(input).toHaveValue(text);
}

async function openFreshWorkbench(page: import("@playwright/test").Page) {
  await page.goto("/workbench");
  await expect(page.getByRole("heading", { name: /把小说改成/ })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "新建改编" }).click();
}

test("keeps input and explains clearly when backend is unavailable", async ({ page }) => {
  await openFreshWorkbench(page);
  const input = page.getByPlaceholder("粘贴至少三章小说文本...");
  await replaceNovelInput(page, threeChapterNovel);

  await page.route("http://127.0.0.1:8000/health", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 350));
    await route.abort();
  });
  await page.getByRole("button", { name: "开始分析" }).click();

  await expect(page.getByTestId("action-banner")).toContainText("正在分析章节");
  await expect(page.getByText("后端服务未连接")).toBeVisible();
  await expect(input).toHaveValue(/林夏在档案馆发现一封没有编号的信。/);
  await expect(page.getByRole("button", { name: "开始分析" })).toBeEnabled();
});

test("shows running and success feedback for intake and file upload", async ({ page }) => {
  await page.route("**/api/runs/intake", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 650));
    await route.continue();
  });

  await openFreshWorkbench(page);
  await page.locator('input[type="file"]').setInputFiles({
    name: "三章小说.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(threeChapterNovel),
  });
  await expect(page.getByText("已选择文件：三章小说.txt")).toBeVisible();

  await page.getByRole("button", { name: "开始分析" }).click();
  await expect(page.getByTestId("action-banner")).toContainText("正在分析章节");
  await expect(page.getByRole("button", { name: "正在分析章节..." })).toBeVisible();
  await expect(page.getByText("章节理解已生成")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("章节理解确认")).toBeVisible();
});

test("shows actionable feedback when generation scope is missing", async ({ page }) => {
  await openFreshWorkbench(page);
  await replaceNovelInput(page, threeChapterNovel);
  await page.getByRole("button", { name: "开始分析" }).click();
  await expect(page.getByText("章节理解确认")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("已读懂 3/3 章")).toBeVisible({ timeout: 90_000 });

  const chapterReviewActions = page.locator(".review-workbench").first();
  await expect(chapterReviewActions.getByRole("button", { name: "全部通过" })).toBeEnabled();
  await chapterReviewActions.getByRole("button", { name: "全部通过" }).click();
  await expect(page.getByText("所有章节已通过")).toBeVisible();
  await expect(chapterReviewActions.getByRole("button", { name: "生成 Story Bible 和改编计划" })).toBeEnabled();
  await chapterReviewActions.getByRole("button", { name: "生成 Story Bible 和改编计划" }).click();
  await expect(page.getByText("副编剧建议")).toBeVisible({ timeout: 90_000 });

  const activeScopeChips = page.locator(".scope-chip.active");
  while (await activeScopeChips.count()) {
    await activeScopeChips.first().click();
  }
  await expect(page.getByText("请选择要生成剧本卡的章节")).toBeVisible();

  await page.getByRole("button", { name: "生成每章剧本卡" }).click();
  await expect(page.getByText("还不能生成剧本卡")).toBeVisible();
  await expect(page.getByLabel("副编剧对话流").getByText("请先选择要生成剧本卡的章节。")).toBeVisible();
  await expect(page.getByTestId("toast-viewport").getByText("请先选择要生成剧本卡的章节。")).toBeVisible();
});
