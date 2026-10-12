import { AxiosError } from "axios"
import type { FieldValues, Path, UseFormReturn } from "react-hook-form"

// Shows a 409 from the API under the matching field. Returns true if handled
export function applyConflictError<T extends FieldValues>(
  err: Error,
  form: UseFormReturn<T>,
  field: Path<T>,
  match: RegExp,
  message?: string,
): boolean {
  if (err instanceof AxiosError && err.response?.status === 409) {
    const detail = (err.response.data as { detail?: unknown } | undefined)
      ?.detail
    if (typeof detail === "string" && match.test(detail)) {
      form.setError(field, { type: "server", message: message ?? detail })
      return true
    }
  }
  return false
}

const IMAGE_ERROR_DETAILS = new Set([
  "Invalid image key",
  "Image upload not found",
  "Image must be 5 MB or smaller",
  "Image type does not match",
  "File is not a valid image",
  "Image storage unavailable",
])

// Shows an image check failure from the API (400/503) under the image field
export function applyImageError<T extends FieldValues>(
  err: Error,
  form: UseFormReturn<T>,
): boolean {
  if (
    err instanceof AxiosError &&
    (err.response?.status === 400 || err.response?.status === 503)
  ) {
    const detail = (err.response.data as { detail?: unknown } | undefined)
      ?.detail
    if (typeof detail === "string" && IMAGE_ERROR_DETAILS.has(detail)) {
      form.setError("image_key" as Path<T>, { type: "server", message: detail })
      return true
    }
  }
  return false
}
