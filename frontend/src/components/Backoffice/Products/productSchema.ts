import { z } from "zod"

import type { ProductCreate, ProductUpdate } from "@/client"

const PRICE = /^\d{1,8}(\.\d{1,2})?$/
const WEIGHT = /^\d{1,7}(\.\d{1,3})?$/

// Values stay strings and are converted on submit (see toCreateBody)
export const productSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(255),
  sku: z.string().trim().min(1, "SKU is required").max(100),
  category_uuid: z.string().min(1, "Category is required"),
  price: z.string().trim().regex(PRICE, "Enter a valid price, e.g. 19.99"),
  stock: z.string().trim().regex(/^\d+$/, "Stock must be a whole number ≥ 0"),
  weight: z
    .string()
    .trim()
    .refine(
      (v) => v === "" || (WEIGHT.test(v) && Number(v) > 0),
      "Enter a weight > 0 with up to 3 decimals",
    ),
  description: z.string(),
  // "" means no image
  image_key: z.string(),
})

export type ProductFormValues = z.infer<typeof productSchema>

export const toCreateBody = (v: ProductFormValues): ProductCreate => ({
  name: v.name.trim(),
  sku: v.sku.trim(),
  category_uuid: v.category_uuid,
  price: v.price.trim(),
  stock: Number(v.stock),
  weight: v.weight.trim() || null,
  description: v.description.trim() || null,
  image_key: v.image_key || null,
})

export function toUpdateBody(
  v: ProductFormValues,
  dirty: Partial<Record<keyof ProductFormValues, boolean>>,
): ProductUpdate {
  const full = toCreateBody(v)
  return Object.fromEntries(
    (Object.keys(dirty) as (keyof ProductFormValues)[])
      .filter((k) => dirty[k])
      .map((k) => [k, full[k]]),
  ) as ProductUpdate
}
