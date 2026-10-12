import { queryOptions } from "@tanstack/react-query"

import { ProductCategoriesService, type ProductCategoryPublic } from "@/client"

export type CategoryData = {
  categories: ProductCategoryPublic[]
  byId: Map<string, ProductCategoryPublic>
}

const PAGE = 100

async function fetchAllCategories(): Promise<CategoryData> {
  const all: ProductCategoryPublic[] = []
  let count = Number.POSITIVE_INFINITY
  while (all.length < count) {
    const { data } = await ProductCategoriesService.readCategories({
      query: { skip: all.length, limit: PAGE },
    })
    all.push(...data.data)
    count = data.count
    if (data.data.length === 0) break
  }
  all.sort((a, b) => a.name.localeCompare(b.name))
  return { categories: all, byId: new Map(all.map((c) => [c.id, c])) }
}

export const categoryKeys = { all: ["categories"] as const }

export const categoriesQueryOptions = queryOptions({
  queryKey: categoryKeys.all,
  queryFn: fetchAllCategories,
  staleTime: 5 * 60 * 1000,
})
