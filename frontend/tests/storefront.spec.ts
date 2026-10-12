import { expect, test } from "@playwright/test"
import {
  createCategory,
  createProduct,
  deleteCategory,
  deleteProduct,
} from "./utils/api"

test.use({ storageState: { cookies: [], origins: [] } })

const PRODUCT_COUNT = 13

let category: Awaited<ReturnType<typeof createCategory>>
let products: Awaited<ReturnType<typeof createProduct>>[] = []
let other: Awaited<ReturnType<typeof createCategory>>

test.beforeAll(async () => {
  category = await createCategory()
  other = await createCategory()
  products = []
  for (let i = 0; i < PRODUCT_COUNT; i++) {
    products.push(
      await createProduct(category.id, {
        name: `Zephyr ${Math.random().toString(36).substring(2, 9)}`,
        price: "1234.50",
        weight: "1.250",
        description: "First line\nSecond line",
        stock: i === 0 ? 0 : i === 1 ? 3 : 10,
      }),
    )
  }
})

test.afterAll(async () => {
  for (const product of products) await deleteProduct(product.id)
  await deleteCategory(category.id)
  await deleteCategory(other.id)
})

test("Visitor sees the catalog with category names and login links", async ({
  page,
}) => {
  await page.goto(`/?category=${category.id}`)

  await expect(page).toHaveURL(/\/\?category=/)
  await expect(page.getByTestId("product-grid")).toBeVisible()
  await expect(page.getByTestId("product-card").first()).toContainText(
    category.name,
  )
  await expect(page.getByRole("link", { name: "Log in" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Sign up" })).toBeVisible()
})

test("Catalog does not redirect visitors", async ({ page }) => {
  await page.goto("/")
  await expect(page).toHaveURL("/")
  await expect(page.getByTestId("product-grid")).toBeVisible()
})

test("Picking a category filters the products", async ({ page }) => {
  await page.goto("/")

  await page
    .getByTestId("category-filter")
    .getByRole("link", { name: category.name, exact: true })
    .click()

  await expect(page).toHaveURL(new RegExp(`category=${category.id}`))
  await expect(page.getByTestId("product-card").first()).toContainText(
    category.name,
  )
  for (const card of await page.getByTestId("product-card").all()) {
    await expect(card).toContainText(category.name)
  }
})

test("Empty category shows the empty state and clears the filter", async ({
  page,
}) => {
  await page.goto(`/?category=${other.id}`)

  await expect(page.getByText("No products found")).toBeVisible()
  await page.getByRole("link", { name: "Clear filter" }).click()
  await expect(page).not.toHaveURL(/category=/)
})

test("Invalid search params fall back to defaults", async ({ page }) => {
  await page.goto("/?category=not-a-uuid&page=-3")
  await expect(page.getByTestId("product-grid")).toBeVisible()
})

test("Pagination shows 12 per page and a second page", async ({ page }) => {
  await page.goto(`/?category=${category.id}`)

  await expect(page.getByTestId("product-card")).toHaveCount(12)
  await expect(page.getByTestId("pagination")).toBeVisible()

  await page.getByRole("link", { name: "Go to page 2" }).click()
  await expect(page).toHaveURL(/page=2/)
  await expect(page.getByTestId("product-card")).toHaveCount(1)
})

test("Page beyond the last shows the empty state", async ({ page }) => {
  await page.goto(`/?category=${category.id}&page=9`)

  await expect(page.getByText("No products found")).toBeVisible()
  await page.getByRole("link", { name: "Back to page 1" }).click()
  await expect(page.getByTestId("product-card")).toHaveCount(12)
})

test("Stock badges reflect the stock level", async ({ page }) => {
  await page.goto(`/products/${products[0].id}`)
  await expect(page.getByText("Out of stock")).toBeVisible()

  await page.goto(`/products/${products[1].id}`)
  await expect(page.getByText("Only 3 left")).toBeVisible()

  await page.goto(`/products/${products[2].id}`)
  await expect(page.getByText("In stock")).toBeVisible()
})

test("Searching for a product name finds it", async ({ page }) => {
  const product = products[5]
  await page.goto("/")

  await page.getByTestId("search-input").fill(` ${product.name} `)
  await page.getByTestId("search-input").press("Enter")

  await expect(page).toHaveURL(/\/search\?q=/)
  await expect(
    page.getByRole("heading", { name: `Results for "${product.name}"` }),
  ).toBeVisible()
  await expect(page.getByTestId("search-input")).toHaveValue(product.name)

  // Elasticsearch is updated asynchronously
  await expect(async () => {
    await page.reload()
    await expect(
      page.getByTestId("product-card").filter({ hasText: product.name }),
    ).toBeVisible({ timeout: 1500 })
  }).toPass({ timeout: 15000 })
})

test("Empty search does nothing and /search without q redirects", async ({
  page,
}) => {
  await page.goto("/")
  await page.getByTestId("search-input").fill("   ")
  await page.getByTestId("search-input").press("Enter")
  await expect(page).toHaveURL("/")

  await page.goto("/search")
  await expect(page).toHaveURL("/")
})

test("Product page shows all the product fields", async ({ page }) => {
  const product = products[2]
  await page.goto(`/products/${product.id}`)

  await expect(page.getByRole("heading", { name: product.name })).toBeVisible()
  await expect(page.getByRole("link", { name: category.name })).toBeVisible()
  await expect(page.getByText("$1,234.50")).toBeVisible()
  await expect(page.getByText(product.sku)).toBeVisible()
  await expect(page.getByText("1.250 kg")).toBeVisible()
  await expect(page.getByText("First line")).toBeVisible()

  await page.getByRole("link", { name: category.name }).click()
  await expect(page).toHaveURL(new RegExp(`category=${category.id}`))
})

test("Product page omits weight and description when unset", async ({
  page,
}) => {
  const bare = await createProduct(category.id, {
    weight: null,
    description: null,
  })
  try {
    await page.goto(`/products/${bare.id}`)
    await expect(page.getByRole("heading", { name: bare.name })).toBeVisible()
    await expect(page.getByText("Weight", { exact: true })).toHaveCount(0)
  } finally {
    await deleteProduct(bare.id)
  }
})

test("Back to products returns to the catalog", async ({ page }) => {
  await page.goto(`/products/${products[0].id}`)
  await page.getByRole("link", { name: "Back to products" }).click()
  await expect(page).toHaveURL("/")
})

test("Unknown product id shows the 404 page", async ({ page }) => {
  await page.goto("/products/3f1c1d2e-7a55-4a39-9f3b-0b8f6f3a0c11")
  await expect(page.getByTestId("not-found")).toBeVisible()
})

test("Malformed product id shows the 404 page", async ({ page }) => {
  await page.goto("/products/not-a-uuid")
  await expect(page.getByTestId("not-found")).toBeVisible()
})

test("Header search is full width on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 })
  await page.goto("/")
  const box = await page.getByTestId("search-input").boundingBox()
  expect(box?.width).toBeGreaterThan(280)
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  )
  expect(overflow).toBe(false)
})

test("Search shows an unavailable message on 503", async ({ page }) => {
  await page.route("**/api/v1/products/search*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Search unavailable" }),
    }),
  )
  await page.goto("/search?q=anything")

  await expect(
    page.getByText(
      "Search is temporarily unavailable. Please try again in a moment.",
    ),
  ).toBeVisible()
  await expect(
    page.getByRole("link", { name: "Browse the catalog" }),
  ).toBeVisible()
})
