import { expect, type Page, test } from "@playwright/test"
import {
  createCategory,
  createProduct,
  deleteCategory,
  deleteProductsInCategory,
} from "./utils/api"
import {
  type Customer,
  createCustomer,
  createStockedProducts,
  customerApi,
  customerPage,
} from "./utils/orders"

let category: Awaited<ReturnType<typeof createCategory>>
let product: Awaited<ReturnType<typeof createProduct>>

test.beforeAll(async () => {
  category = await createCategory()
  for (let i = 0; i < 13; i++) {
    product = await createProduct(category.id)
  }
})

test.afterAll(async () => {
  await deleteProductsInCategory(category.id)
  await deleteCategory(category.id)
})

const hasHorizontalScroll = (page: Page) =>
  page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  )

// Buttons and links must expose a name to assistive tech
async function expectAccessibleNames(page: Page) {
  const unnamed = await page
    .locator("button:visible, a[href]:visible, [role=combobox]:visible")
    .evaluateAll((els) =>
      els
        .filter((el) => {
          if (
            el.closest("[class*='tsqd'], [id*='devtools'], [class*='Devtools']")
          )
            return false
          const label =
            el.getAttribute("aria-label") ||
            el.getAttribute("aria-labelledby") ||
            (el as HTMLElement).innerText?.trim() ||
            el.textContent?.trim() ||
            el.querySelector("img[alt]:not([alt=''])")?.getAttribute("alt")
          return !label
        })
        .map((el) => el.outerHTML.slice(0, 120)),
    )
  expect(unnamed).toEqual([])
}

test.describe("Mobile (360px)", () => {
  test.use({ viewport: { width: 360, height: 780 } })

  test("Storefront pages have no horizontal scroll", async ({ page }) => {
    for (const url of [
      `/?category=${category.id}`,
      `/?category=${category.id}&page=2`,
      `/search?q=${encodeURIComponent(product.name)}`,
      `/products/${product.id}`,
    ]) {
      await page.goto(url)
      await expect(page.locator("main")).toBeVisible()
      await page.waitForLoadState("networkidle")
      expect(await hasHorizontalScroll(page), url).toBe(false)
    }
  })

  test("Auth screens have no horizontal scroll", async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 360, height: 780 },
      storageState: { cookies: [], origins: [] },
    })
    const page = await context.newPage()
    for (const url of ["/login", "/signup", "/recover-password"]) {
      await page.goto(url)
      await page.waitForLoadState("networkidle")
      expect(await hasHorizontalScroll(page), url).toBe(false)
    }
    await context.close()
  })

  test("Backoffice pages have no horizontal page scroll", async ({ page }) => {
    for (const url of [
      "/admin",
      `/admin/products?category=${category.id}`,
      "/admin/categories",
      "/admin/imports",
      "/admin/users",
      "/admin/settings",
    ]) {
      await page.goto(url)
      await page.waitForLoadState("networkidle")
      expect(await hasHorizontalScroll(page), url).toBe(false)
    }
  })

  test("Backoffice dialogs fit the screen", async ({ page }) => {
    await page.goto(`/admin/products?category=${category.id}`)
    await expect(async () => {
      await page.getByRole("button", { name: "Add Product" }).click()
      await expect(page.getByRole("dialog")).toBeVisible({ timeout: 1000 })
    }).toPass()
    const box = await page.getByRole("dialog").boundingBox()
    expect(box?.x).toBeGreaterThanOrEqual(0)
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(360)
    expect(box?.height).toBeLessThanOrEqual(780)
  })

  test("Header shows search under the logo row", async ({ page }) => {
    await page.goto("/")
    const logo = await page
      .getByRole("link", { name: /Ecommerce/ })
      .first()
      .boundingBox()
    const search = await page.getByTestId("search-input").boundingBox()
    expect(search!.y).toBeGreaterThan(logo!.y + logo!.height - 1)
  })
})

test.describe("Keyboard", () => {
  test("Header controls are reachable with Tab", async ({ browser }) => {
    const context = await browser.newContext({
      storageState: { cookies: [], origins: [] },
    })
    const page = await context.newPage()
    await page.goto("/")
    await expect(page.getByTestId("product-grid")).toBeVisible()

    const seen: string[] = []
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press("Tab")
      seen.push(
        await page.evaluate(() => {
          const el = document.activeElement as HTMLElement | null
          return (
            el?.getAttribute("data-testid") ||
            el?.getAttribute("aria-label") ||
            el?.innerText?.trim() ||
            ""
          )
        }),
      )
    }
    expect(seen).toContain("search-input")
    expect(seen).toContain("theme-button")
    expect(seen).toContain("Log in")
    expect(seen).toContain("Sign up")
    await context.close()
  })

  test("Search can be submitted with the keyboard", async ({ browser }) => {
    const context = await browser.newContext({
      storageState: { cookies: [], origins: [] },
    })
    const page = await context.newPage()
    await page.goto("/")
    await page.getByTestId("search-input").focus()
    await page.keyboard.type("abc")
    await page.keyboard.press("Enter")
    await expect(page).toHaveURL(/\/search\?q=abc/)
    await context.close()
  })

  test("Category chips, cards and pagination are keyboard operable", async ({
    browser,
  }) => {
    const context = await browser.newContext({
      storageState: { cookies: [], origins: [] },
    })
    const page = await context.newPage()
    await page.goto(`/?category=${category.id}`)
    await expect(page.getByTestId("product-card")).toHaveCount(12)

    const chip = page
      .getByTestId("category-filter")
      .getByRole("link", { name: "All" })
    await chip.focus()
    await expect(chip).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page).not.toHaveURL(/category=/)

    await page.goto(`/?category=${category.id}`)
    const page2 = page.getByRole("link", { name: "Go to page 2" })
    await page2.focus()
    await page.keyboard.press("Enter")
    await expect(page).toHaveURL(/page=2/)

    const card = page
      .getByTestId("product-card")
      .first()
      .getByRole("link")
      .first()
    await expect(async () => {
      await card.focus()
      await expect(card).toBeFocused({ timeout: 1000 })
    }).toPass()
    await page.keyboard.press("Enter")
    await expect(page).toHaveURL(/\/products\//)
    await context.close()
  })

  test("Interactive elements expose accessible names", async ({ browser }) => {
    const context = await browser.newContext({
      storageState: { cookies: [], origins: [] },
    })
    const page = await context.newPage()
    for (const url of [
      `/?category=${category.id}`,
      `/products/${product.id}`,
      "/login",
    ]) {
      await page.goto(url)
      await page.waitForLoadState("networkidle")
      await expectAccessibleNames(page)
    }
    await context.close()
  })

  test("Backoffice icon buttons expose accessible names", async ({ page }) => {
    for (const url of [
      `/admin/products?category=${category.id}`,
      "/admin/categories",
      "/admin/imports",
    ]) {
      await page.goto(url)
      await page.waitForLoadState("networkidle")
      await expectAccessibleNames(page)
    }
  })

  test("Dialogs open with the keyboard, trap focus and close on Escape", async ({
    page,
  }) => {
    await page.goto("/admin/categories")
    const add = page.getByRole("button", { name: "Add Category" })
    await expect(async () => {
      await add.focus()
      await page.keyboard.press("Enter")
      await expect(page.getByRole("dialog")).toBeVisible({ timeout: 1000 })
    }).toPass()

    for (let i = 0; i < 8; i++) {
      await page.keyboard.press("Tab")
      expect(
        await page.evaluate(
          () => !!document.activeElement?.closest("[role=dialog]"),
        ),
      ).toBe(true)
    }

    await page.keyboard.press("Escape")
    await expect(page.getByRole("dialog")).not.toBeVisible()
    await expect(add).toBeFocused()
  })

  test("Form fields have labels", async ({ page }) => {
    await page.goto(`/admin/products?category=${category.id}`)
    await expect(async () => {
      await page.getByRole("button", { name: "Add Product" }).click()
      await expect(page.getByRole("dialog")).toBeVisible({ timeout: 1000 })
    }).toPass()
    const dialog = page.getByRole("dialog")
    for (const label of [
      "Name",
      "SKU",
      "Category",
      "Price",
      "Stock",
      "Weight (kg)",
      "Description",
    ]) {
      await expect(dialog.getByLabel(label).first()).toBeVisible()
    }
  })

  test("User menu works with the keyboard", async ({ page }) => {
    await page.goto("/")
    const menu = page.getByTestId("user-menu")
    await expect(async () => {
      await menu.focus()
      await page.keyboard.press("Enter")
      await expect(
        page.getByRole("menuitem", { name: "Backoffice" }),
      ).toBeVisible({ timeout: 1000 })
    }).toPass()
    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("Escape")
    await expect(menu).toBeFocused()
  })
})

test.describe("Cart and orders", () => {
  let customer: Customer
  let order: Awaited<
    ReturnType<Awaited<ReturnType<typeof customerApi>>["place"]>
  >
  let cartProducts: Awaited<
    ReturnType<typeof createStockedProducts>
  >["products"]

  test.beforeAll(async () => {
    customer = await createCustomer()
    const api = await customerApi(customer)
    const placed = await createStockedProducts(1)
    await api.add(placed.products[0].id)
    order = await api.place()
    cartProducts = (await createStockedProducts(2)).products
    for (const product of cartProducts) await api.add(product.id)
  })

  test("Pages have no horizontal scroll on mobile", async ({ browser }) => {
    const { context, page } = await customerPage(browser, customer, {
      width: 360,
      height: 780,
    })
    for (const url of [
      "/cart",
      "/checkout",
      "/orders",
      `/orders/${order.id}`,
    ]) {
      await page.goto(url)
      await page.waitForLoadState("networkidle")
      expect(await hasHorizontalScroll(page), url).toBe(false)
    }
    await context.close()
  })

  test.describe("Admin", () => {
    test.use({ viewport: { width: 360, height: 780 } })

    test("Backoffice orders have no horizontal page scroll", async ({
      page,
    }) => {
      for (const url of ["/admin/orders", `/admin/orders/${order.id}`]) {
        await page.goto(url)
        await page.waitForLoadState("networkidle")
        expect(await hasHorizontalScroll(page), url).toBe(false)
      }
    })
  })

  test("Interactive elements expose accessible names", async ({
    browser,
    page,
  }) => {
    const customerSession = await customerPage(browser, customer)
    for (const url of [
      "/cart",
      "/checkout",
      "/orders",
      `/orders/${order.id}`,
    ]) {
      await customerSession.page.goto(url)
      await customerSession.page.waitForLoadState("networkidle")
      await expectAccessibleNames(customerSession.page)
    }
    await customerSession.context.close()

    for (const url of ["/admin/orders", `/admin/orders/${order.id}`]) {
      await page.goto(url)
      await page.waitForLoadState("networkidle")
      await expectAccessibleNames(page)
    }
  })

  test("The cart is operable with the keyboard", async ({ browser }) => {
    const { context, page } = await customerPage(browser, customer)
    const [first, second] = cartProducts
    await page.goto("/cart")
    const total = page.getByTestId("cart-total")
    const before = await total.innerText()

    const quantity = page.getByLabel(`Quantity for ${first.name}`, {
      exact: true,
    })
    await quantity.focus()
    await page.keyboard.press("ControlOrMeta+a")
    await page.keyboard.type("2")
    await expect(total).not.toHaveText(before)

    const remove = page.getByRole("button", {
      name: `Remove ${second.name}`,
      exact: true,
    })
    await remove.focus()
    await page.keyboard.press("Enter")
    await expect(page.getByTestId("cart-line")).toHaveCount(1)
    await context.close()
  })

  test("Cancelling an order is operable with the keyboard", async ({
    page,
  }) => {
    await page.goto("/admin/orders")
    const cancel = page.getByRole("button", {
      name: `Cancel order ${order.number}`,
    })
    await expect(async () => {
      await cancel.focus()
      await page.keyboard.press("Enter")
      await expect(page.getByRole("dialog")).toBeVisible({ timeout: 1000 })
    }).toPass()
    expect(
      await page.evaluate(
        () => !!document.activeElement?.closest("[role=dialog]"),
      ),
    ).toBe(true)

    await page.keyboard.press("Escape")
    await expect(page.getByRole("dialog")).not.toBeVisible()
    await expect(cancel).toBeFocused()
  })
})
