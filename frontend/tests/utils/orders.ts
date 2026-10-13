import type { Browser } from "@playwright/test"
import type { OrderPublic } from "../../src/client"
import { createCategory, createProduct, createUser } from "./api"
import { randomEmail, randomPassword } from "./random"
import { logInUser } from "./user"

export type Customer = { email: string; password: string }

export async function createCustomer(): Promise<Customer> {
  const customer = { email: randomEmail(), password: randomPassword() }
  await createUser(customer)
  return customer
}

// Own category and products per test: stock and price edits never leak between
// tests that run in parallel
export async function createStockedProducts(
  count: number,
  overrides: Parameters<typeof createProduct>[1] = {},
) {
  const category = await createCategory()
  const products = []
  for (let i = 0; i < count; i++) {
    products.push(await createProduct(category.id, overrides))
  }
  return { category, products }
}

// Customer-side API calls with the customer's own token (api.ts acts as admin)
export async function customerApi({ email, password }: Customer) {
  const base = `${process.env.VITE_API_URL}/api/v1`
  const form = new URLSearchParams({ username: email, password })
  const login = await fetch(`${base}/login/access-token`, {
    method: "POST",
    body: form,
  })
  const { access_token } = await login.json()
  const call = async (method: string, path: string, body?: unknown) => {
    const res = await fetch(`${base}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${access_token}`,
        "Content-Type": "application/json",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (!res.ok)
      throw new Error(`${method} ${path}: ${res.status} ${await res.text()}`)
    return res.json()
  }
  return {
    add: (productId: string, quantity = 1) =>
      call("POST", "/cart/items", { product_id: productId, quantity }),
    place: async (): Promise<OrderPublic> => {
      const cart = await call("GET", "/cart/")
      return call("POST", "/cart/place", {
        order_id: cart.id,
        expected_total: cart.total_price,
      })
    },
  }
}

export async function customerPage(
  browser: Browser,
  customer: Customer,
  viewport?: { width: number; height: number },
) {
  const context = await browser.newContext({
    storageState: { cookies: [], origins: [] },
    viewport,
  })
  const page = await context.newPage()
  await logInUser(page, customer.email, customer.password)
  return { context, page }
}

export async function newCustomerPage(browser: Browser) {
  const customer = await createCustomer()
  return { customer, ...(await customerPage(browser, customer)) }
}
