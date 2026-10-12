import { useSuspenseQuery } from "@tanstack/react-query"

import { categoriesQueryOptions } from "@/lib/queries/categories"

export function useCategories() {
  const { data } = useSuspenseQuery(categoriesQueryOptions)
  const categoryName = (id: string) =>
    data.byId.get(id)?.name ?? "Uncategorized"
  return { ...data, categoryName }
}
