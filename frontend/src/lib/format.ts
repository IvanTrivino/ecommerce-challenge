const priceFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
})
const dateFormatter = new Intl.DateTimeFormat("en-US", { dateStyle: "medium" })

// Number() is only used to format: values have at most 10 significant digits
export const formatPrice = (value: string | number) =>
  priceFormatter.format(Number(value))
export const formatWeight = (value: string | number) =>
  `${Number(value).toFixed(3)} kg`
// Matches the backend's order number: the first 8 hex chars of the id, uppercased
export const orderNumber = (id: string) =>
  id.replace(/-/g, "").slice(0, 8).toUpperCase()
export const formatDate = (iso: string) => dateFormatter.format(new Date(iso))

// 1024-based units labelled KB/MB, to match the "10 MB" wording elsewhere
export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}
