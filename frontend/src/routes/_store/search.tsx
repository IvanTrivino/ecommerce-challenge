import { useQuery } from "@tanstack/react-query"
import {
  createFileRoute,
  Link,
  redirect,
  stripSearchParams,
  useNavigate,
} from "@tanstack/react-router"
import { AxiosError } from "axios"
import { z } from "zod"

import { PaginationBar } from "@/components/Store/PaginationBar"
import { ProductGrid } from "@/components/Store/ProductGrid"
import { ProductGridSkeleton } from "@/components/Store/ProductGridSkeleton"
import { Button } from "@/components/ui/button"
import { pageTitle, STORE_PAGE_SIZE } from "@/config"
import { productSearchQueryOptions } from "@/lib/queries/products"

const searchSearch = z.object({
  q: z
    .string()
    .catch("")
    .transform((q) => q.trim().slice(0, 200))
    .default(""),
  page: z.number().int().positive().catch(1).default(1),
})

export const Route = createFileRoute("/_store/search")({
  component: SearchResults,
  search: { middlewares: [stripSearchParams({ page: 1 })] },
  validateSearch: searchSearch,
  beforeLoad: ({ search }) => {
    if (!search.q) throw redirect({ to: "/" })
  },
  head: () => ({
    meta: [{ title: pageTitle("Search") }],
  }),
})

function SearchResults() {
  const { q, page } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const { data, isPending, error } = useQuery(
    productSearchQueryOptions({ q, page, pageSize: STORE_PAGE_SIZE }),
  )

  if (error) {
    const unavailable =
      error instanceof AxiosError && error.response?.status === 503
    return (
      <div
        className="flex flex-col items-center gap-3 py-16 text-center"
        data-testid="search-error"
      >
        <p className="text-lg font-medium">
          {unavailable
            ? "Search is temporarily unavailable. Please try again in a moment."
            : "Something went wrong while searching."}
        </p>
        <Button variant="outline" asChild>
          <Link to="/">Browse the catalog</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight break-words">
          Results for "{q}"
        </h1>
        {data && (
          <p className="text-muted-foreground">
            {data.count} {data.count === 1 ? "product" : "products"} found
          </p>
        )}
      </div>
      {isPending ? (
        <ProductGridSkeleton />
      ) : (
        <>
          <ProductGrid
            products={data.data}
            empty={
              <>
                <p className="text-lg font-medium">No products found</p>
                {page > 1 && data.count > 0 ? (
                  <Button variant="outline" asChild>
                    <Link to="/search" search={{ q, page: 1 }}>
                      Back to page 1
                    </Link>
                  </Button>
                ) : null}
              </>
            }
          />
          <PaginationBar
            page={page}
            pageSize={STORE_PAGE_SIZE}
            total={data.count}
            onPageChange={(p) =>
              navigate({ search: (prev) => ({ ...prev, page: p }) })
            }
          />
        </>
      )}
    </div>
  )
}
