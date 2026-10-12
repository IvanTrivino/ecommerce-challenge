import {
  LoginService,
  ProductCategoriesService,
  type ProductCategoryCreate,
  type ProductCreate,
  ProductsService,
  UsersService,
} from "../../src/client"
import { client } from "../../src/client/client.gen"
import { firstSuperuser, firstSuperuserPassword } from "../config"
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

export const deleteProduct = async (id: string) => {
  await asAdmin()
  await ProductsService.deleteProduct({ path: { product_id: id } })
}
