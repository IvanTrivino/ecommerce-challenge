import { expect, type Page } from "@playwright/test"

// Client-side paginated tables: page forward until a row with the text shows up
export async function findRow(page: Page, text: string) {
  const row = page.getByRole("row").filter({ hasText: text })
  // the table must have rendered its rows before we start paging
  await expect(page.getByRole("row").nth(1)).toBeVisible()
  await page.waitForLoadState("networkidle")
  const next = page.getByRole("button", { name: "Go to next page" })
  for (let i = 0; i < 20; i++) {
    if ((await row.count()) > 0) break
    if ((await next.count()) === 0 || (await next.isDisabled())) break
    await next.click()
  }
  await expect(row).toBeVisible()
  return row
}
