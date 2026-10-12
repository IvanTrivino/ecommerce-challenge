import { expect, test } from "@playwright/test"
import {
  createCategory,
  createProduct,
  deleteCategory,
  deleteProduct,
} from "./utils/api"
import { randomCategoryName, slugify } from "./utils/random"
import { findRow } from "./utils/ui"

test("Creating a category auto-fills the code from the name", async ({
  page,
}) => {
  const name = randomCategoryName()
  await page.goto("/admin/categories")

  await page.getByRole("button", { name: "Add Category" }).click()
  await page.getByPlaceholder("Name").fill(name)
  await expect(page.getByPlaceholder("Code")).toHaveValue(slugify(name))

  await page.getByRole("button", { name: "Save" }).click()
  await expect(page.getByText("Category created successfully")).toBeVisible()
  await expect(page.getByRole("dialog")).not.toBeVisible()

  const row = await findRow(page, name)
  await expect(row).toContainText(slugify(name))
})

test("Editing the code by hand stops the auto-fill", async ({ page }) => {
  await page.goto("/admin/categories")

  await expect(async () => {
    await page.getByRole("button", { name: "Add Category" }).click()
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 1000 })
  }).toPass()
  await page.getByPlaceholder("Name").fill("First Name")
  await page.getByPlaceholder("Code").fill("custom-code")
  await page.getByPlaceholder("Name").fill("Second Name")

  await expect(page.getByPlaceholder("Code")).toHaveValue("custom-code")
})

test("Edit a category and delete an empty one", async ({ page }) => {
  const category = await createCategory()
  const renamed = randomCategoryName()
  await page.goto("/admin/categories")

  let row = await findRow(page, category.name)
  await row.getByRole("button").click()
  await page.getByRole("menuitem", { name: "Edit Category" }).click()
  await page.getByPlaceholder("Name").fill(renamed)
  await page.getByRole("button", { name: "Save" }).click()
  await expect(page.getByText("Category updated successfully")).toBeVisible()

  row = await findRow(page, renamed)
  await row.getByRole("button").click()
  await page.getByRole("menuitem", { name: "Delete Category" }).click()
  await page.getByRole("button", { name: "Delete", exact: true }).click()

  await expect(page.getByText("Category deleted successfully")).toBeVisible()
  await expect(page.getByRole("row").filter({ hasText: renamed })).toHaveCount(
    0,
  )
})

test("Deleting a category that still has products shows an error", async ({
  page,
}) => {
  const category = await createCategory()
  const product = await createProduct(category.id)
  try {
    await page.goto("/admin/categories")

    const row = await findRow(page, category.name)
    await row.getByRole("button").click()
    await page.getByRole("menuitem", { name: "Delete Category" }).click()
    await page.getByRole("button", { name: "Delete", exact: true }).click()

    await expect(
      page.getByText("Cannot delete a category that still has products"),
    ).toBeVisible()
    await expect(page.getByRole("dialog")).not.toBeVisible()
    await findRow(page, category.name)
  } finally {
    await deleteProduct(product.id)
    await deleteCategory(category.id)
  }
})

test("A duplicate code is shown under the Code field", async ({ page }) => {
  const category = await createCategory()
  try {
    await page.goto("/admin/categories")

    await page.getByRole("button", { name: "Add Category" }).click()
    await page.getByPlaceholder("Name").fill(randomCategoryName())
    await page.getByPlaceholder("Code").fill(category.code)
    await page.getByRole("button", { name: "Save" }).click()

    await expect(
      page.getByText("A category with this code already exists"),
    ).toBeVisible()
    await expect(page.getByRole("dialog")).toBeVisible()
  } finally {
    await deleteCategory(category.id)
  }
})

test("Name and code are required", async ({ page }) => {
  await page.goto("/admin/categories")

  await page.getByRole("button", { name: "Add Category" }).click()
  await page.getByRole("button", { name: "Save" }).click()

  await expect(page.getByText("Name is required")).toBeVisible()
  await expect(page.getByText("Code is required")).toBeVisible()
})
