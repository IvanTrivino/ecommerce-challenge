import { readFile } from "node:fs/promises"
import { expect, type Page, test } from "@playwright/test"
import {
  deleteImportedCategory,
  findCategoryByName,
  waitForNoActiveImport,
} from "./utils/api"
import { bigCsvFile, csvFile, makeImportCsv, txtFile } from "./utils/imports"

// One active import at a time: the specs below must not overlap
test.describe.configure({ mode: "serial" })

const categories: string[] = []

test.beforeEach(async () => {
  await waitForNoActiveImport()
})

test.afterAll(async () => {
  for (const name of categories) await deleteImportedCategory(name)
})

const newImport = () => {
  const data = makeImportCsv()
  categories.push(data.category)
  return data
}

const uploadAndStart = async (page: Page, csv: string) => {
  await page.goto("/admin/imports")
  await page.getByLabel("CSV file").setInputFiles(csvFile(csv))
  const start = page.getByRole("button", { name: "Import", exact: true })
  await expect(start).toBeEnabled()
  await start.click()
  await expect(page).toHaveURL(/\/admin\/imports\/[0-9a-f-]{36}$/)
}

const importFinished = (page: Page) =>
  expect(
    page.getByRole("progressbar", { name: "Import progress" }),
  ).toHaveAttribute("aria-valuenow", "100", { timeout: 30_000 })

let first: ReturnType<typeof makeImportCsv>
let firstUrl = ""

test("Uploading a CSV imports it and shows the summary", async ({ page }) => {
  first = newImport()
  await uploadAndStart(page, first.csv)
  firstUrl = page.url()

  await importFinished(page)
  await expect(page.getByTestId("import-status")).toHaveText(
    "Completed with errors",
  )
  const { expected } = first
  await expect(page.getByTestId("import-count-created")).toHaveText(
    `${expected.created}`,
  )
  await expect(page.getByTestId("import-count-updated")).toHaveText(
    `${expected.updated}`,
  )
  await expect(page.getByTestId("import-count-unchanged")).toHaveText(
    `${expected.unchanged}`,
  )
  await expect(page.getByTestId("import-count-errors")).toHaveText(
    `${expected.errors}`,
  )
  await expect(page.getByTestId("import-count-blank")).toHaveText(
    `${expected.blank}`,
  )
  await expect(page.getByTestId("import-count-categories")).toHaveText(
    `${expected.categories}`,
  )
  await expect(page.getByText("Import finished")).toBeVisible()
})

test("The errors table and the report list the rejected rows", async ({
  page,
}) => {
  await page.goto(firstUrl)

  const rows = page.getByRole("row").filter({ hasText: first.prefix })
  await expect(rows).toHaveCount(2) // lines 4 and 5 carry a SKU; line 6 has none
  await expect(page.getByRole("row", { name: /^4\b/ })).toContainText(
    "price: must be a number like 12.50",
  )
  await expect(page.getByRole("row", { name: /^5\b/ })).toContainText(
    "stock: must be a whole number ≥ 0",
  )
  await expect(page.getByRole("row", { name: /^6\b/ })).toContainText(
    "name: required",
  )

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByTestId("download-error-report").click(),
  ])
  const report = await readFile((await download.path()) as string, "utf-8")
  expect(report.startsWith("line,sku,error\r\n")).toBe(true)
  expect(report.trim().split("\r\n")).toHaveLength(1 + first.errorLines.length)
})

test("Imported products are in the backoffice and the storefront", async ({
  page,
}) => {
  const category = await findCategoryByName(first.category)
  expect(category).toBeDefined()

  await page.goto(`/admin/products?category=${category?.id}`)
  await expect(page.getByRole("row")).toHaveCount(3) // header + 2 products
  // The last row for a SKU wins
  await expect(
    page.getByRole("row").filter({ hasText: first.name }),
  ).toContainText("$94.99")

  await expect(async () => {
    await page.goto(`/search?q=${encodeURIComponent(first.name)}`)
    await expect(page.getByText(first.name).first()).toBeVisible({
      timeout: 1000,
    })
  }).toPass({ timeout: 20_000 })
})

test("Invalid files are rejected in the browser", async ({ page }) => {
  const requests: string[] = []
  page.on("request", (r) => {
    if (r.url().includes("/product-imports") || r.url().includes(":9000"))
      requests.push(r.url())
  })
  await page.goto("/admin/imports")

  await page.getByLabel("CSV file").setInputFiles(txtFile())
  await expect(page.getByRole("alert")).toHaveText("Choose a .csv file")

  await page.getByLabel("CSV file").setInputFiles(bigCsvFile())
  await expect(page.getByRole("alert")).toHaveText(
    "CSV must be 10 MB or smaller",
  )
  expect(requests).toEqual([])
})

test("A failed import shows its reason and can be retried", async ({
  page,
}) => {
  await uploadAndStart(
    page,
    "name,sku,category,stock\r\nMug,NOPRICE-1,Whatever,1",
  )

  await expect(page.getByTestId("import-status")).toHaveText("Failed")
  await expect(page.getByRole("alert")).toContainText("Missing columns: price")

  const retried = page.waitForRequest(
    (r) => r.method() === "POST" && r.url().endsWith("/retry"),
  )
  await page.getByRole("button", { name: "Retry" }).click()
  await retried
  // The file is still bad: it fails again with the same reason
  await expect(page.getByTestId("import-status")).toHaveText("Failed")
  await expect(page.getByRole("alert")).toContainText("Missing columns: price")
})

test("Starting an import while another is active shows an inline message", async ({
  page,
}) => {
  const { csv } = newImport()
  await page.route("**/api/v1/product-imports/", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 409,
          json: { detail: "Another import is in progress" },
        })
      : route.continue(),
  )
  await page.goto("/admin/imports")
  await page.getByLabel("CSV file").setInputFiles(csvFile(csv))
  await page.getByRole("button", { name: "Import", exact: true }).click()

  await expect(page.getByText("Another import is in progress")).toBeVisible()
  await expect(page).toHaveURL(/\/admin\/imports$/)
})

test("An import keeps running when you leave the page", async ({ page }) => {
  const { csv, expected } = newImport()
  await uploadAndStart(page, csv)
  const importUrl = page.url()

  await page.goto("/admin/products")
  await page.goto(importUrl)

  await importFinished(page)
  await expect(page.getByTestId("import-count-created")).toHaveText(
    `${expected.created}`,
  )
})

test("The sidebar and the products page lead to the imports", async ({
  page,
}) => {
  await page.goto("/admin/products")
  await expect(
    page.getByRole("link", { name: "Imports", exact: true }),
  ).toBeVisible()

  await page.getByRole("link", { name: "Import CSV" }).click()

  await expect(page).toHaveURL(/\/admin\/imports$/)
})
