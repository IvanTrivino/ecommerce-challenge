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
export const formatDate = (iso: string) => dateFormatter.format(new Date(iso))
