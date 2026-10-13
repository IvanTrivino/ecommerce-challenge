import type { ProductImageUploadRequest } from "@/client"
import { isStorageForbidden, storageErrorCode } from "@/lib/storageUpload"

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

export function storageErrorMessage(err: unknown): string {
  const code = storageErrorCode(err)
  if (code === "EntityTooLarge") return "Image must be 5 MB or smaller"
  if (code === "InvalidPolicyDocument") return "Image type not allowed"
  if (isStorageForbidden(err)) return "Upload link expired, try again"
  return "Image upload failed"
}
