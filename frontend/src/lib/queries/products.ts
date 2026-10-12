import { keepPreviousData, queryOptions } from "@tanstack/react-query"

import { ProductsService } from "@/client"

type ListParams = { category?: string; page: number; pageSize: number }
type SearchParams = { q: string; page: number; pageSize: number }

export const productKeys = {
  all: ["products"] as const,
  list: (p: ListParams) => ["products", "list", p] as const,
  search: (p: SearchParams) => ["products", "search", p] as const,
  detail: (id: string) => ["products", "detail", id] as const,
}

export const productListQueryOptions = ({
  category,
  page,
  pageSize,
}: ListParams) =>
  queryOptions({
    queryKey: productKeys.list({ category, page, pageSize }),
    queryFn: async () =>
      (
        await ProductsService.readProducts({
          query: {
            category_uuid: category,
            skip: (page - 1) * pageSize,
            limit: pageSize,
          },
        })
      ).data,
    placeholderData: keepPreviousData,
  })

export const productSearchQueryOptions = ({
  q,
  page,
  pageSize,
}: SearchParams) =>
  queryOptions({
    queryKey: productKeys.search({ q, page, pageSize }),
    queryFn: async () =>
      (
        await ProductsService.searchProducts({
          query: { q, skip: (page - 1) * pageSize, limit: pageSize },
        })
      ).data,
    placeholderData: keepPreviousData,
    retry: false,
  })

export const productQueryOptions = (id: string) =>
  queryOptions({
    queryKey: productKeys.detail(id),
    queryFn: async () =>
      (await ProductsService.readProduct({ path: { product_id: id } })).data,
  })
