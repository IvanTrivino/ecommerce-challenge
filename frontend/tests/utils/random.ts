export const randomEmail = () =>
  `test_${Math.random().toString(36).substring(7)}@example.com`

export const randomPassword = () => `${Math.random().toString(36).substring(2)}`

export const slugify = (text: string) =>
  text
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^\w-]+/g, "")

const randomToken = () => Math.random().toString(36).substring(2, 9)

export const randomSku = () => `SKU-${randomToken().toUpperCase()}`

export const randomCategoryName = () => `Category ${randomToken()}`

export const randomProductName = () => `Product ${randomToken()}`
