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
