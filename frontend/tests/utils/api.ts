import {
  LoginService,
  OrdersService,
  ProductCategoriesService,
  type ProductCategoryCreate,
  type ProductCreate,
  ProductImportsService,
  ProductsService,
  type ProductUpdate,
  UsersService,
} from "../../src/client"
import { client } from "../../src/client/client.gen"
import { firstSuperuser, firstSuperuserPassword } from "../config"
import { PNG_1PX } from "./images"
import {
  randomCategoryName,
  randomProductName,
  randomSku,
  slugify,
} from "./random"

let token = ""

client.setConfig({
  baseURL: `${process.env.VITE_API_URL}`,
  auth: () => token,
})

// Logs in once as the first superuser; every helper below acts as that user
async function asAdmin() {
  if (!token) {
    const { data } = await LoginService.loginAccessToken({
      body: { username: firstSuperuser, password: firstSuperuserPassword },
    })
    token = data.access_token
  }
}

export const createUser = async ({
  email,
  password,
  isSuperuser = false,
}: {
  email: string
  password: string
  isSuperuser?: boolean
}) => {
  await asAdmin()
  const response = await UsersService.createUser({
    body: {
      email,
      password,
      full_name: "Test User",
      is_superuser: isSuperuser,
    },
  })
  return response.data
}

export const createCategory = async (
  overrides: Partial<ProductCategoryCreate> = {},
) => {
  await asAdmin()
  const name = overrides.name ?? randomCategoryName()
  const response = await ProductCategoriesService.createCategory({
    body: { name, code: slugify(name).slice(0, 50), ...overrides },
  })
  return response.data
}

export const deleteCategory = async (id: string) => {
  await asAdmin()
  await ProductCategoriesService.deleteCategory({ path: { category_id: id } })
}

export const createProduct = async (
  categoryId: string,
  overrides: Partial<ProductCreate> = {},
) => {
  await asAdmin()
  const response = await ProductsService.createProduct({
    body: {
      name: randomProductName(),
      sku: randomSku(),
      category_uuid: categoryId,
      price: "19.99",
      stock: 10,
      ...overrides,
    },
  })
  return response.data
}

export const updateProduct = async (id: string, body: ProductUpdate) => {
  await asAdmin()
  return (
    await ProductsService.updateProduct({ path: { product_id: id }, body })
  ).data
}

export const readProduct = async (id: string) => {
  await asAdmin()
  return (await ProductsService.readProduct({ path: { product_id: id } })).data
}

export const cancelOrderAsAdmin = async (id: string) => {
  await asAdmin()
  return (await OrdersService.cancelOrder({ path: { order_id: id } })).data
}

export const deleteProduct = async (id: string) => {
  await asAdmin()
  await ProductsService.deleteProduct({ path: { product_id: id } })
}

export const deleteProductsInCategory = async (categoryId: string) => {
  await asAdmin()
  const { data } = await ProductsService.readProducts({
    query: { category_uuid: categoryId, limit: 100 },
  })
  for (const product of data.data) await deleteProduct(product.id)
}

// Uploads a real image to storage and returns its key, for `image_key`
export const uploadProductImage = async (
  body: Buffer = PNG_1PX,
  contentType: "image/jpeg" | "image/png" | "image/webp" = "image/png",
) => {
  await asAdmin()
  const { data } = await ProductsService.presignProductImage({
    body: { content_type: contentType, size: body.length },
  })
  const form = new FormData()
  for (const [name, value] of Object.entries(data.fields))
    form.append(name, value)
  form.append("file", new Blob([new Uint8Array(body)], { type: contentType }))
  const res = await fetch(data.url, { method: "POST", body: form })
  if (!res.ok)
    throw new Error(`Upload failed: ${res.status} ${await res.text()}`)
  return data.key
}

export const listImports = async () => {
  await asAdmin()
  return (
    await ProductImportsService.readProductImports({ query: { limit: 20 } })
  ).data
}

// Waits until no import is active, so a serial spec can start its own (only
// one import can run at a time)
export const waitForNoActiveImport = async (timeoutMs = 60_000) => {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const { data } = await listImports()
    if (!data.some((i) => i.status === "pending" || i.status === "running"))
      return
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error("An import stayed active")
}

export const findCategoryByName = async (name: string) => {
  await asAdmin()
  for (let skip = 0; ; skip += 100) {
    const { data } = await ProductCategoriesService.readCategories({
      query: { skip, limit: 100 },
    })
    const found = data.data.find((c) => c.name === name)
    if (found) return found
    if (data.data.length < 100) return undefined
  }
}

// Categories are created by the imports themselves
export const deleteImportedCategory = async (name: string) => {
  const category = await findCategoryByName(name)
  if (!category) return
  await deleteProductsInCategory(category.id)
  await deleteCategory(category.id)
}
