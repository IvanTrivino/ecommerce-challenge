import { keepPreviousData, queryOptions } from "@tanstack/react-query"

import { ProductImportsService } from "@/client"
import { IMPORT_POLL_MS, isImportActive } from "@/lib/productImports"

const LIST_POLL_MS = 2000
const ERRORS_PAGE = 500

export const importKeys = {
  all: ["productImports"] as const,
  list: (page: number) => ["productImports", "list", page] as const,
  detail: (id: string) => ["productImports", "detail", id] as const,
  errors: (id: string, page: number) =>
    ["productImports", "errors", id, page] as const,
}

export const importListQueryOptions = (page: number, pageSize: number) =>
  queryOptions({
    queryKey: importKeys.list(page),
    queryFn: async () =>
      (
        await ProductImportsService.readProductImports({
          query: { skip: (page - 1) * pageSize, limit: pageSize },
        })
      ).data,
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.data.some((i) => isImportActive(i.status))
        ? LIST_POLL_MS
        : false,
  })

export const importQueryOptions = (id: string) =>
  queryOptions({
    queryKey: importKeys.detail(id),
    queryFn: async () =>
      (
        await ProductImportsService.readProductImport({
          path: { import_id: id },
        })
      ).data,
    refetchInterval: (query) =>
      isImportActive(query.state.data?.status) ? IMPORT_POLL_MS : false,
  })

export const importErrorsQueryOptions = (
  id: string,
  page: number,
  pageSize: number,
) =>
  queryOptions({
    queryKey: importKeys.errors(id, page),
    queryFn: async () =>
      (
        await ProductImportsService.readProductImportErrors({
          path: { import_id: id },
          query: { skip: (page - 1) * pageSize, limit: pageSize },
        })
      ).data,
    placeholderData: keepPreviousData,
  })

// All stored errors, for the downloadable report (at most 1000: two requests)
export async function fetchAllImportErrors(id: string) {
  const all: { line: number; sku: string | null; message: string }[] = []
  let count = Number.POSITIVE_INFINITY
  while (all.length < count) {
    const { data } = await ProductImportsService.readProductImportErrors({
      path: { import_id: id },
      query: { skip: all.length, limit: ERRORS_PAGE },
    })
    all.push(...data.data)
    count = data.count
    if (data.data.length === 0) break
  }
  return all
}
