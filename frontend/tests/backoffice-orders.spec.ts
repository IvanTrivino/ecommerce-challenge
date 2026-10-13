import { expect, type Page, test } from "@playwright/test"
import { cancelOrderAsAdmin, readProduct } from "./utils/api"
import {
  createCustomer,
  createStockedProducts,
  customerApi,
} from "./utils/orders"

const orderRow = (page: Page, number: string) =>
  page.getByRole("row").filter({ hasText: number })

async function placedOrder(quantity = 1, stock = 10) {
  const customer = await createCustomer()
  const { products } = await createStockedProducts(1, { stock })
  const api = await customerApi(customer)
  await api.add(products[0].id, quantity)
  return { customer, product: products[0], order: await api.place() }
}

test("Complete an order from the list", async ({ page }) => {
  const { order } = await placedOrder()

  await page.goto("/admin/orders")
  const row = orderRow(page, order.number)
  await expect(row).toBeVisible()
  await row.getByTestId("complete-order").click()
  await expect(
    page.getByRole("dialog", {
      name: `Mark order #${order.number} as completed?`,
    }),
  ).toBeVisible()
  await page.getByTestId("confirm-order-action").click()
  await expect(page.getByText(`Order #${order.number} completed`)).toBeVisible()
  await expect(row).toBeHidden()

  await page.getByRole("tab", { name: "Completed" }).click()
  const completed = orderRow(page, order.number)
  await expect(completed).toBeVisible()
  await expect(completed.getByTestId("order-state")).toHaveText("Completed")
  await expect(completed.getByTestId("cancel-order")).toBeDisabled()
  await expect(completed.getByTestId("complete-order")).toBeDisabled()
})

test("Cancelling restores the stock", async ({ page }) => {
  const { product, order } = await placedOrder(2, 8)
  expect((await readProduct(product.id)).stock).toBe(6)

  await page.goto(`/admin/orders/${order.id}`)
  await expect(page.getByTestId("order-customer")).toHaveText(order.user_email)
  await page.getByTestId("cancel-order").click()
  await expect(page.getByRole("dialog")).toContainText("go back into stock")
  await page.getByTestId("confirm-order-action").click()

  await expect(page.getByTestId("order-state")).toHaveText("Cancelled")
  await expect(page.getByTestId("cancel-order")).toBeDisabled()
  expect((await readProduct(product.id)).stock).toBe(8)

  await page.goto(`/products/${product.id}`)
  await expect(page.getByText("In stock")).toBeVisible()
})

test("Drafts are listed in their own tab and cannot be actioned", async ({
  page,
}) => {
  const customer = await createCustomer()
  const { products } = await createStockedProducts(1)
  await (await customerApi(customer)).add(products[0].id)

  await page.goto("/admin/orders?tab=draft")

  const row = page.getByRole("row").filter({ hasText: customer.email })
  await expect(row).toBeVisible()
  await expect(row.getByTestId("order-state")).toHaveText("Draft")
  await expect(row.getByTestId("cancel-order")).toBeDisabled()
  await expect(row.getByTestId("complete-order")).toBeDisabled()
})

test("All placed shows every placed state", async ({ page }) => {
  const done = await placedOrder()
  const open = await placedOrder()
  await cancelOrderAsAdmin(done.order.id)

  await page.goto("/admin/orders?tab=placed")

  await expect(orderRow(page, done.order.number)).toBeVisible()
  await expect(orderRow(page, open.order.number)).toBeVisible()
})

test("A conflicting action shows an error and the real state", async ({
  page,
}) => {
  const { order } = await placedOrder()
  await page.goto("/admin/orders?tab=placed")
  const row = orderRow(page, order.number)
  await row.getByTestId("cancel-order").click()
  await expect(page.getByRole("dialog")).toBeVisible()

  await cancelOrderAsAdmin(order.id)
  await page.getByTestId("confirm-order-action").click()

  await expect(
    page.getByText("Only in-progress orders can be cancelled"),
  ).toBeVisible()
  await expect(row.getByTestId("order-state")).toHaveText("Cancelled")
})
