import { expect, type Page, test } from "@playwright/test"
import {
  createCategory,
  createProduct,
  deleteCategory,
  deleteProduct,
  deleteProductsInCategory,
} from "./utils/api"
import {
  randomCategoryName,
  randomProductName,
  randomSku,
} from "./utils/random"
import { findRow } from "./utils/ui"

let category: Awaited<ReturnType<typeof createCategory>>

test.beforeAll(async () => {
  category = await createCategory()
})

test.afterAll(async () => {
  await deleteProductsInCategory(category.id)
  await deleteCategory(category.id)
})

const openAddDialog = async (page: Page) => {
  await page.goto(`/admin/products?category=${category.id}`)
  await page.getByRole("button", { name: "Add Product" }).click()
}

const fillProduct = async (
  page: Page,
  values: { name: string; sku: string; price: string; stock?: string },
) => {
  const dialog = page.getByRole("dialog")
  await dialog.getByPlaceholder("Name").fill(values.name)
  await dialog.getByPlaceholder("SKU").fill(values.sku)
  await dialog.getByLabel("Category").click()
  await page.getByRole("option", { name: category.name }).click()
  await dialog.getByPlaceholder("0.00", { exact: true }).fill(values.price)
  if (values.stock) await dialog.getByLabel("Stock").fill(values.stock)
}

test("Create a product and see it on the storefront", async ({ page }) => {
  const name = randomProductName()
  const sku = randomSku()
  await openAddDialog(page)

  await fillProduct(page, { name, sku, price: "29.99", stock: "7" })
  await page.getByRole("button", { name: "Save" }).click()

  await expect(page.getByText("Product created successfully")).toBeVisible()
  await expect(page.getByRole("dialog")).not.toBeVisible()

  const row = page.getByRole("row").filter({ hasText: sku })
  await expect(row).toBeVisible()
  await expect(row).toContainText(category.name)
  await expect(row).toContainText("$29.99")

  await page.goto(`/?category=${category.id}`)
  const card = page.getByTestId("product-card").filter({ hasText: name })
  await expect(card).toBeVisible()
  await expect(card).toContainText(category.name)
})

test("Renaming a category updates product tables without a reload", async ({
  page,
}) => {
  const cat = await createCategory()
  const product = await createProduct(cat.id)
  const renamed = randomCategoryName()
  try {
    await page.goto("/admin/categories")
    const catRow = await findRow(page, cat.name)
    await catRow.getByRole("button").click()
    await page.getByRole("menuitem", { name: "Edit Category" }).click()
    await page.getByPlaceholder("Name").fill(renamed)
    await page.getByRole("button", { name: "Save" }).click()
    await expect(page.getByText("Category updated successfully")).toBeVisible()

    await page.getByRole("link", { name: "Products" }).click()
    await expect(page.getByRole("heading", { name: "Products" })).toBeVisible()
    await expect(
      page.getByRole("row").filter({ hasText: product.sku }),
    ).toContainText(renamed)
  } finally {
    await deleteProduct(product.id)
    await deleteCategory(cat.id)
  }
})

test("A duplicate SKU is shown under the SKU field", async ({ page }) => {
  const product = await createProduct(category.id)
  await openAddDialog(page)

  await fillProduct(page, {
    name: randomProductName(),
    sku: product.sku,
    price: "5",
  })
  await page.getByRole("button", { name: "Save" }).click()

  await expect(
    page.getByText("A product with this SKU already exists"),
  ).toBeVisible()
  await expect(page.getByRole("dialog")).toBeVisible()
})

test("Editing only the stock sends only the stock", async ({ page }) => {
  const product = await createProduct(category.id)
  await page.goto(`/admin/products?category=${category.id}`)

  const row = page.getByRole("row").filter({ hasText: product.sku })
  await row.getByRole("button").click()
  await page.getByRole("menuitem", { name: "Edit Product" }).click()
  await page.getByLabel("Stock").fill("42")

  const requestPromise = page.waitForRequest(
    (req) =>
      req.method() === "PATCH" && req.url().includes("/api/v1/products/"),
  )
  await page.getByRole("button", { name: "Save" }).click()
  const request = await requestPromise

  expect(request.postDataJSON()).toEqual({ stock: 42 })
  await expect(page.getByText("Product updated successfully")).toBeVisible()
  await expect(
    page.getByRole("row").filter({ hasText: product.sku }),
  ).toContainText("42")
})

test("Deleting a product removes it from the table and the storefront", async ({
  page,
}) => {
  const product = await createProduct(category.id)
  await page.goto(`/admin/products?category=${category.id}`)

  const row = page.getByRole("row").filter({ hasText: product.sku })
  await row.getByRole("button").click()
  await page.getByRole("menuitem", { name: "Delete Product" }).click()
  await page.getByRole("button", { name: "Delete", exact: true }).click()

  await expect(page.getByText("Product deleted successfully")).toBeVisible()
  await expect(row).toHaveCount(0)

  await page.goto(`/products/${product.id}`)
  await expect(page.getByTestId("not-found")).toBeVisible()
})

test("Price, stock and weight are validated", async ({ page }) => {
  await openAddDialog(page)

  await page.getByPlaceholder("0.00", { exact: true }).fill("abc")
  await page.getByPlaceholder("0.000").fill("0")
  // blur first: validation messages shift the button while it is clicked
  await page.getByRole("heading", { name: "Add Product" }).click()
  await page.getByRole("button", { name: "Save" }).click()

  await expect(page.getByText("Enter a valid price, e.g. 19.99")).toBeVisible()
  await expect(
    page.getByText("Enter a weight > 0 with up to 3 decimals"),
  ).toBeVisible()
  await expect(page.getByText("Name is required")).toBeVisible()
  await expect(page.getByText("Category is required")).toBeVisible()

  await page.getByPlaceholder("0.00", { exact: true }).fill("1.234")
  await page.getByRole("button", { name: "Save" }).click()
  await expect(page.getByText("Enter a valid price, e.g. 19.99")).toBeVisible()
})

test("Category filter and overview counts work", async ({ page }) => {
  const product = await createProduct(category.id)

  await page.goto("/admin/products")
  await page.getByTestId("category-select").click()
  await page.getByRole("option", { name: category.name }).click()
  await expect(page).toHaveURL(new RegExp(`category=${category.id}`))
  await expect(
    page.getByRole("row").filter({ hasText: product.sku }),
  ).toBeVisible()

  await page.goto("/admin")
  await expect(page.getByTestId("stat-products")).toContainText(/\d+/)
  await page.getByTestId("stat-categories").click()
  await expect(page).toHaveURL("/admin/categories")
})
