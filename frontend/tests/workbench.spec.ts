import { expect, test } from "@playwright/test";

test("converts sample novel into editable YAML", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Novel2Script Agent Studio" })).toBeVisible();
  await page.getByRole("button", { name: "开始改编" }).click();

  await expect(page.getByText("状态：succeeded")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("generate_report")).toBeVisible();
  await expect(page.getByText("重新校验 YAML")).toBeVisible();

  await page.getByRole("button", { name: "重新校验 YAML" }).click();
  await expect(page.getByText("校验通过")).toBeVisible();
  await expect(page.getByRole("button", { name: "下载当前 YAML" })).toBeEnabled();
  await expect(page.getByText("下载 script.yaml")).toBeVisible();
});
