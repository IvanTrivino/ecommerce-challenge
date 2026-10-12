import { useQuery } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { z } from "zod"

import { CategoryFilter } from "@/components/Store/CategoryFilter"
import { PaginationBar } from "@/components/Store/PaginationBar"
import { ProductGrid } from "@/components/Store/ProductGrid"
import { ProductGridSkeleton } from "@/components/Store/ProductGridSkeleton"
import { Button } from "@/components/ui/button"
import { pageTitle, STORE_PAGE_SIZE } from "@/config"
import { productListQueryOptions } from "@/lib/queries/products"

const catalogSearch = z.object({
  category: z.uuid().optional().catch(undefined),
  page: z.number().int().positive().catch(1).default(1),
})

export const Route = createFileRoute("/_store/")({
  component: Catalog,
  validateSearch: catalogSearch,
  loaderDeps: ({ search }) => search,
  loader: ({ context, deps }) => {
    // warm the cache without blocking, so paging keeps the old page visible
    void context.queryClient.prefetchQuery(
      productListQueryOptions({ ...deps, pageSize: STORE_PAGE_SIZE }),
    )
  },
  head: () => ({
    meta: [{ title: pageTitle("Products") }],
  }),
})

function Catalog() {
  const { category, page } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const { data, isPending, isError, refetch } = useQuery(
    productListQueryOptions({ category, page, pageSize: STORE_PAGE_SIZE }),
  )

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Products</h1>
        <p className="text-muted-foreground">Browse our catalog</p>
      </div>
      <CategoryFilter selected={category} />
      {isPending ? (
        <ProductGridSkeleton />
      ) : isError ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <p>We couldn't load the products.</p>
          <Button variant="outline" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : (
        <>
          <ProductGrid
            products={data.data}
            empty={
              <>
                <p className="text-lg font-medium">No products found</p>
                {category ? (
                  <Button variant="outline" asChild>
                    <Link to="/" search={{ page: 1 }}>
                      Clear filter
                    </Link>
                  </Button>
                ) : null}
                {page > 1 && data.count > 0 ? (
                  <Button variant="outline" asChild>
                    <Link to="/" search={{ category, page: 1 }}>
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
