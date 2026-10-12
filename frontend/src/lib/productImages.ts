import axios from "axios"

import type { ProductImageUpload, ProductImageUploadRequest } from "@/client"

type ImageContentType = ProductImageUploadRequest["content_type"]

// Mirrors the backend (PRODUCT_IMAGE_MAX_BYTES, allowed content types)
export const IMAGE_TYPES: readonly ImageContentType[] = [
  "image/jpeg",
  "image/png",
  "image/webp",
]
export const IMAGE_MAX_BYTES = 5 * 1024 * 1024
export const IMAGE_ACCEPT = IMAGE_TYPES.join(",")
export const IMAGE_HINT = "JPEG, PNG or WebP, up to 5 MB"

export function validateImageFile(file: File): string | null {
  if (!IMAGE_TYPES.includes(file.type as ImageContentType))
    return "Choose a JPEG, PNG or WebP image"
  if (file.size === 0) return "The file is empty"
  if (file.size > IMAGE_MAX_BYTES) return "Image must be 5 MB or smaller"
  return null
}

// Straight to object storage: the default axios instance carries no auth
// header, which would break the storage signature and leak the token
export async function uploadToStorage(
  ticket: Pick<ProductImageUpload, "url" | "fields">,
  file: File,
  {
    onProgress,
    signal,
  }: { onProgress?: (percent: number) => void; signal?: AbortSignal } = {},
): Promise<void> {
  const body = new FormData()
  for (const [name, value] of Object.entries(ticket.fields))
    body.append(name, value)
  body.append("file", file) // storage ignores any field after the file
  await axios.post(ticket.url, body, {
    signal,
    onUploadProgress: (e) =>
      e.total && onProgress?.(Math.round((e.loaded / e.total) * 100)),
  })
}

export function storageErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err) && err.response) {
    const data: unknown = err.response.data
    const code =
      typeof data === "string" ? /<Code>([^<]+)<\/Code>/.exec(data)?.[1] : null
    if (code === "EntityTooLarge") return "Image must be 5 MB or smaller"
    if (code === "InvalidPolicyDocument") return "Image type not allowed"
    if (err.response.status === 403) return "Upload link expired, try again"
  }
  return "Image upload failed"
}
