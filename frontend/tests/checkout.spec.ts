import { expect, test } from "@playwright/test"
import { updateProduct } from "./utils/api"
import { waitForEmailHtml } from "./utils/mailpit"
import {
  createCustomer,
  createStockedProducts,
  newCustomerPage,
} from "./utils/orders"

const addButton = (name: string) => ({ name: `Add ${name} to cart` })

test("Visitor '+ Add' asks to log in and comes back", async ({ browser }) => {
  const customer = await createCustomer()
  const { category, products } = await createStockedProducts(1)
  const context = await browser.newContext({
    storageState: { cookies: [], origins: [] },
  })
  const page = await context.newPage()

  await page.goto(`/?category=${category.id}`)
  await page.getByRole("button", addButton(products[0].name)).click()
  await expect(page).toHaveURL(/\/login\?redirect=/)

  await page.getByTestId("email-input").fill(customer.email)
  await page.getByTestId("password-input").fill(customer.password)
  await page.getByRole("button", { name: "Log In" }).click()

  await expect(page).toHaveURL(new RegExp(`/\\?category=${category.id}`))
  await expect(page.getByTestId("user-menu")).toBeVisible()
  await context.close()
})

test("Add, change quantity and remove", async ({ browser }) => {
  const { context, page } = await newCustomerPage(browser)
  const { category, products } = await createStockedProducts(2)
  const [a, b] = products
  await Promise.all([
    updateProduct(a.id, { price: "10.00" }),
    updateProduct(b.id, { price: "5.50" }),
  ])

  await page.goto(`/?category=${category.id}`)
  await page.getByRole("button", addButton(a.name)).click()
  await expect(page.getByTestId("cart-count")).toHaveText("1")
  await page.getByRole("button", addButton(a.name)).click()
  await expect(page.getByTestId("cart-count")).toHaveText("2")

  await page.goto(`/products/${b.id}`)
  await page.getByRole("button", addButton(b.name)).click()
  await expect(page.getByTestId("cart-count")).toHaveText("3")

  await page.goto("/cart")
  await expect(page.getByTestId("cart-line")).toHaveCount(2)
  await expect(
    page.getByLabel(`Quantity for ${a.name}`, { exact: true }),
  ).toHaveValue("2")
  await expect(
    page.getByLabel(`Quantity for ${b.name}`, { exact: true }),
  ).toHaveValue("1")
  await expect(page.getByTestId("cart-total")).toHaveText("$25.50")

  await page.getByLabel(`Quantity for ${b.name}`, { exact: true }).fill("3")
  await expect(page.getByTestId("cart-total")).toHaveText("$36.50")

  for (const name of [a.name, b.name]) {
    await page
      .getByRole("button", { name: `Remove ${name}`, exact: true })
      .click()
  }
  await expect(page.getByText("Your cart is empty")).toBeVisible()
  await context.close()
})

test("Place an order and receive the email", async ({ browser, request }) => {
  const { customer, context, page } = await newCustomerPage(browser)
  const { products } = await createStockedProducts(2)
  const [a, b] = products

  await page.goto(`/products/${a.id}`)
  await page.getByRole("button", addButton(a.name)).click()
  await expect(page.getByTestId("cart-count")).toHaveText("1")
  await page.goto(`/products/${b.id}`)
  await page.getByRole("button", addButton(b.name)).click()
  await expect(page.getByTestId("cart-count")).toHaveText("2")

  await page.goto("/cart")
  await page.getByTestId("checkout-button").click()
  await expect(page).toHaveURL(/\/checkout$/)
  await page.getByTestId("place-order").click()

  await expect(page).toHaveURL(/\/orders\/[0-9a-f-]{36}$/)
  await expect(page.getByTestId("order-placed-alert")).toBeVisible()
  await expect(page.getByTestId("order-state")).toHaveText("In progress")
  await expect(page.getByText(a.name)).toBeVisible()
  await expect(page.getByText(b.name)).toBeVisible()
  await expect(page.getByTestId("cart-count")).toBeHidden()
  const number = (await page.getByRole("heading", { level: 1 }).innerText())
    .replace("Order #", "")
    .trim()

  const html = await waitForEmailHtml({
    request,
    query: `to:${customer.email} subject:"Order #${number} confirmed"`,
    timeout: 30_000,
  })
  expect(html).toContain(`Order #${number}`)
  expect(html).toContain(a.name)
  expect(html).toContain(b.name)

  await page.getByTestId("user-menu").click()
  await page.getByRole("menuitem", { name: "My orders" }).click()
  await expect(page).toHaveURL(/\/orders$/)
  await page.getByTestId("my-order").filter({ hasText: number }).click()
  await expect(page).toHaveURL(/\/orders\/[0-9a-f-]{36}$/)
  await expect(page.getByTestId("order-placed-alert")).toBeHidden()
  await context.close()
})

test("A price change before placing asks to review the total", async ({
  browser,
}) => {
  const { context, page } = await newCustomerPage(browser)
  const { products } = await createStockedProducts(1)
  const [product] = products
  await updateProduct(product.id, { price: "10.00" })
  await page.goto(`/products/${product.id}`)
  await page.getByRole("button", addButton(product.name)).click()
  await expect(page.getByTestId("cart-count")).toHaveText("1")

  await page.goto("/checkout")
  await expect(page.getByTestId("checkout-total")).toHaveText("$10.00")
  await updateProduct(product.id, { price: "99.99" })
  await page.getByTestId("place-order").click()

  await expect(page.getByTestId("place-error")).toContainText(
    "Some prices changed",
  )
  await expect(page.getByTestId("checkout-total")).toHaveText("$99.99")
  await page.getByTestId("place-order").click()
  await expect(page).toHaveURL(/\/orders\/[0-9a-f-]{36}$/)
  await context.close()
})

test("An unavailable line blocks the checkout until it is lowered", async ({
  browser,
}) => {
  const { context, page } = await newCustomerPage(browser)
  const { products } = await createStockedProducts(1)
  const [product] = products
  await page.goto(`/products/${product.id}`)
  await page.getByLabel("Quantity").fill("3")
  await page.getByRole("button", addButton(product.name)).click()
  await expect(page.getByTestId("cart-count")).toHaveText("3")
  await updateProduct(product.id, { stock: 1 })

  await page.goto("/cart")
  await expect(page.getByText("Only 1 left")).toBeVisible()
  await expect(page.getByTestId("checkout-button")).toBeDisabled()

  await page
    .getByLabel(`Quantity for ${product.name}`, { exact: true })
    .fill("1")
  await expect(page.getByTestId("checkout-button")).toBeEnabled()
  await context.close()
})

test("A sold-out product cannot be added", async ({ browser }) => {
  const { context, page } = await newCustomerPage(browser)
  const { category, products } = await createStockedProducts(1, { stock: 0 })

  await page.goto(`/?category=${category.id}`)
  const button = page.getByRole("button", {
    name: `${products[0].name} is sold out`,
  })
  await expect(button).toBeDisabled()
  await expect(button).toHaveText("Sold out")
  await context.close()
})

test("A customer cannot open the backoffice orders", async ({ browser }) => {
  const { context, page } = await newCustomerPage(browser)

  await page.goto("/admin/orders")

  await expect(page).toHaveURL("/")
  await context.close()
})
