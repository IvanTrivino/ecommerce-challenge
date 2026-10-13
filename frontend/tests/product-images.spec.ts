import { expect, type Page, test } from "@playwright/test"
import {
  createCategory,
  createProduct,
  deleteCategory,
  deleteProductsInCategory,
  uploadProductImage,
} from "./utils/api"
import { bigPngFile, pngFile, svgFile } from "./utils/images"
import { randomProductName, randomSku } from "./utils/random"

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

const openEditDialog = async (page: Page, sku: string) => {
  await page.goto(`/admin/products?category=${category.id}`)
  const row = page.getByRole("row").filter({ hasText: sku })
  await row.getByRole("button").click()
  await page.getByRole("menuitem", { name: "Edit Product" }).click()
}

const imageInput = (page: Page) =>
  page.getByRole("dialog").getByLabel("Image", { exact: true })

const fillProduct = async (page: Page, name: string, sku: string) => {
  const dialog = page.getByRole("dialog")
  await dialog.getByPlaceholder("Name").fill(name)
  await dialog.getByPlaceholder("SKU").fill(sku)
  await dialog.getByLabel("Category").click()
  await page.getByRole("option", { name: category.name }).click()
  await dialog.getByPlaceholder("0.00", { exact: true }).fill("12.50")
}

// Holds every request to storage until `release` is called
const gateStorage = async (page: Page) => {
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route("**/localhost:9000/**", async (route) => {
    await gate
    await route.continue()
  })
  return release
}

const storefrontCard = (page: Page, name: string) =>
  page.getByTestId("product-card").filter({ hasText: name })

test("Add a product with an image and see it everywhere", async ({ page }) => {
  const name = randomProductName()
  const sku = randomSku()
  await openAddDialog(page)

  await imageInput(page).setInputFiles(pngFile())
  await expect(
    page.getByTestId("product-image-preview").locator("img"),
  ).toBeVisible()
  const save = page.getByRole("button", { name: "Save" })
  await expect(save).toBeEnabled()
  await fillProduct(page, name, sku)
  await save.click()
  await expect(page.getByText("Product created successfully")).toBeVisible()

  const row = page.getByRole("row").filter({ hasText: sku })
  await expect(row.getByTestId("product-image")).toHaveAttribute(
    "src",
    /\/products\/[0-9a-f-]{36}\.png$/,
  )

  await page.goto(`/?category=${category.id}`)
  const image = storefrontCard(page, name).getByTestId("product-image")
  await expect(image).toBeVisible()
  await expect
    .poll(() => image.evaluate((i: HTMLImageElement) => i.naturalWidth))
    .toBeGreaterThan(0)

  await storefrontCard(page, name).click()
  await expect(page.getByRole("img", { name })).toBeVisible()
})

test("Replace and then remove an image", async ({ page }) => {
  const product = await createProduct(category.id, {
    image_key: await uploadProductImage(),
  })
  const before = product.image_url

  await openEditDialog(page, product.sku)
  await imageInput(page).setInputFiles(pngFile("other.png"))
  const save = page.getByRole("button", { name: "Save" })
  await expect(save).toBeEnabled()
  await save.click()
  await expect(page.getByText("Product updated successfully")).toBeVisible()

  await page.goto(`/?category=${category.id}`)
  const image = storefrontCard(page, product.name).getByTestId("product-image")
  await expect(image).toBeVisible()
  expect(await image.getAttribute("src")).not.toBe(before)

  await openEditDialog(page, product.sku)
  await page.getByRole("button", { name: "Remove" }).click()
  await page.getByRole("button", { name: "Save" }).click()
  await expect(page.getByText("Product updated successfully")).toBeVisible()

  await page.goto(`/?category=${category.id}`)
  await expect(
    storefrontCard(page, product.name).getByTestId("product-image-placeholder"),
  ).toBeVisible()
})

// The native file picker (or switching apps) blurs the window, which closes the
// actions menu; the dialog must survive it. setInputFiles never opens the picker,
// so blur the window by hand.
test("The edit dialog stays open when the window loses focus", async ({
  page,
}) => {
  const product = await createProduct(category.id)

  await openEditDialog(page, product.sku)
  const dialog = page.getByRole("dialog")
  await expect(dialog).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event("blur")))
  await expect(page.getByRole("menu")).toBeHidden()
  await expect(dialog).toBeVisible()

  // No image upload: other tests here count every request to storage, and the
  // product list would load its thumbnail
  const name = randomProductName()
  await dialog.getByPlaceholder("Name").fill(name)
  await dialog.getByRole("button", { name: "Save" }).click()
  await expect(page.getByText("Product updated successfully")).toBeVisible()
  await expect(page.getByRole("row").filter({ hasText: name })).toBeVisible()
})

test("Invalid files are rejected without any request", async ({ page }) => {
  const requests: string[] = []
  page.on("request", (req) => {
    if (req.url().includes("/images/presign") || req.url().includes(":9000"))
      requests.push(req.url())
  })
  await openAddDialog(page)

  await imageInput(page).setInputFiles(svgFile())
  await expect(page.getByText("Choose a JPEG, PNG or WebP image")).toBeVisible()

  await imageInput(page).setInputFiles(bigPngFile())
  await expect(page.getByText("Image must be 5 MB or smaller")).toBeVisible()

  expect(requests).toEqual([])
})

test("Save is disabled while the image uploads", async ({ page }) => {
  const release = await gateStorage(page)
  await openAddDialog(page)

  await imageInput(page).setInputFiles(pngFile())
  await expect(page.getByRole("progressbar")).toBeVisible()
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled()

  release()
  await expect(page.getByRole("button", { name: "Save" })).toBeEnabled()
  await expect(page.getByRole("progressbar")).not.toBeVisible()
})

test("A broken image falls back to the placeholder", async ({ page }) => {
  const product = await createProduct(category.id, {
    image_key: await uploadProductImage(),
  })
  await page.route("**/products/*.png", (route) => route.abort())

  await page.goto(`/?category=${category.id}`)

  await expect(
    storefrontCard(page, product.name).getByTestId("product-image-placeholder"),
  ).toBeVisible()
})

test("Cancelling the dialog aborts the upload", async ({ page }) => {
  const release = await gateStorage(page)
  await openAddDialog(page)
  await imageInput(page).setInputFiles(pngFile())
  await expect(page.getByRole("progressbar")).toBeVisible()

  await page.getByRole("button", { name: "Cancel" }).click()
  await expect(page.getByRole("dialog")).not.toBeVisible()
  release()

  await page.getByRole("button", { name: "Add Product" }).click()
  await expect(
    page.getByTestId("product-image-preview").locator("img"),
  ).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Save" })).toBeEnabled()
})
