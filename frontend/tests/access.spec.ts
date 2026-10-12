import { expect, test } from "@playwright/test"
import { firstSuperuser, firstSuperuserPassword } from "./config.ts"
import {
  createCategory,
  createProduct,
  createUser,
  deleteCategory,
  deleteProduct,
} from "./utils/api"
import { randomEmail, randomPassword } from "./utils/random"
import { logInUser } from "./utils/user"

test.use({ storageState: { cookies: [], origins: [] } })

test("Customer lands on the storefront without a Backoffice entry", async ({
  page,
}) => {
  const email = randomEmail()
  const password = randomPassword()
  await createUser({ email, password })

  await logInUser(page, email, password)

  await expect(page).toHaveURL("/")
  await page.getByTestId("user-menu").click()
  await expect(page.getByRole("menuitem", { name: "My account" })).toBeVisible()
  await expect(page.getByRole("menuitem", { name: "Backoffice" })).toHaveCount(
    0,
  )
})

test("Admin lands on the backoffice and can open the storefront", async ({
  page,
}) => {
  await logInUser(page, firstSuperuser, firstSuperuserPassword, {
    admin: true,
  })

  await expect(page).toHaveURL("/admin")
  await page.getByRole("link", { name: "View store" }).click()
  await expect(page).toHaveURL("/")
  // the first click can land before the page is interactive
  await expect(async () => {
    await page.getByTestId("user-menu").click()
    await expect(
      page.getByRole("menuitem", { name: "Backoffice" }),
    ).toBeVisible({ timeout: 1000 })
  }).toPass()
})

test("Logged-in users are redirected away from the auth screens", async ({
  page,
}) => {
  const email = randomEmail()
  const password = randomPassword()
  await createUser({ email, password })
  await logInUser(page, email, password)

  for (const path of ["/login", "/signup", "/recover-password"]) {
    await page.goto(path)
    await expect(page).toHaveURL("/")
  }
})

test("Customer is redirected away from the backoffice", async ({ page }) => {
  const email = randomEmail()
  const password = randomPassword()
  await createUser({ email, password })
  await logInUser(page, email, password)

  await page.goto("/admin/products")
  await expect(page).toHaveURL("/")
})

test("Visitor is sent to log in and returns to the requested page", async ({
  page,
}) => {
  await page.goto("/admin/products")
  await expect(page).toHaveURL(/\/login\?redirect=%2Fadmin%2Fproducts/)

  await page.getByTestId("email-input").fill(firstSuperuser)
  await page.getByTestId("password-input").fill(firstSuperuserPassword)
  await page.getByRole("button", { name: "Log In" }).click()

  await expect(page).toHaveURL("/admin/products")
})

test("Unsafe redirect targets are ignored after login", async ({ page }) => {
  await page.goto("/login?redirect=//evil.example.com")

  await page.getByTestId("email-input").fill(firstSuperuser)
  await page.getByTestId("password-input").fill(firstSuperuserPassword)
  await page.getByRole("button", { name: "Log In" }).click()

  await expect(page).toHaveURL("/admin")
})

test("A corrupted token on a public page logs the visitor out silently", async ({
  page,
}) => {
  const category = await createCategory()
  const product = await createProduct(category.id)
  try {
    await page.goto("/")
    await page.evaluate(() => localStorage.setItem("access_token", "bad"))
    await page.goto(`/?category=${category.id}`)

    await expect(page.getByTestId("product-grid")).toBeVisible()
    await expect(page.getByRole("link", { name: "Log in" })).toBeVisible()
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem("access_token")))
      .toBeNull()
    await expect(page).toHaveURL(/\/\?category=/)
  } finally {
    await deleteProduct(product.id)
    await deleteCategory(category.id)
  }
})

test("A corrupted token on /account redirects to login", async ({ page }) => {
  await page.goto("/")
  await page.evaluate(() => localStorage.setItem("access_token", "bad"))
  await page.goto("/account")

  await expect(page).toHaveURL(/\/login\?redirect=%2Faccount/)
})
