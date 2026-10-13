import { useQuery } from "@tanstack/react-query"
import {
  createFileRoute,
  Link,
  stripSearchParams,
  useNavigate,
} from "@tanstack/react-router"
import { FileUp, Package } from "lucide-react"
import { z } from "zod"

import AddProduct from "@/components/Backoffice/Products/AddProduct"
import { columns } from "@/components/Backoffice/Products/columns"
import { DataTable } from "@/components/Common/DataTable"
import PendingProducts from "@/components/Pending/PendingProducts"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ADMIN_PAGE_SIZE, pageTitle } from "@/config"
import { useCategories } from "@/hooks/useCategories"
import { productListQueryOptions } from "@/lib/queries/products"

const productsSearch = z.object({
  category: z.uuid().optional().catch(undefined),
  page: z.number().int().positive().catch(1).default(1),
})

export const Route = createFileRoute("/admin/products")({
  component: Products,
  search: { middlewares: [stripSearchParams({ page: 1 })] },
  validateSearch: productsSearch,
  head: () => ({
    meta: [{ title: pageTitle("Products") }],
  }),
})

const ALL = "all"

function Products() {
  const { category, page } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const { categories } = useCategories()
  const { data, isPending } = useQuery(
    productListQueryOptions({ category, page, pageSize: ADMIN_PAGE_SIZE }),
  )

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Products</h1>
          <p className="text-muted-foreground">Manage the product catalog</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" asChild>
            <Link to="/admin/imports">
              <FileUp />
              Import CSV
            </Link>
          </Button>
          <AddProduct />
        </div>
      </div>
      <div className="w-full sm:w-64">
        <Select
          value={category ?? ALL}
          onValueChange={(value) =>
            navigate({
              search: {
                category: value === ALL ? undefined : value,
                page: 1,
              },
            })
          }
        >
          <SelectTrigger
            className="w-full"
            aria-label="Filter by category"
            data-testid="category-select"
          >
            <SelectValue placeholder="All categories" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All categories</SelectItem>
            {categories.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {isPending ? (
        <PendingProducts />
      ) : data && data.data.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="mb-4 rounded-full bg-muted p-4">
            <Package className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold">No products yet</h3>
          <p className="text-muted-foreground">Add a product to get started</p>
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={data?.data ?? []}
          pagination={{
            page,
            pageSize: ADMIN_PAGE_SIZE,
            total: data?.count ?? 0,
            onPageChange: (p) =>
              navigate({ search: (prev) => ({ ...prev, page: p }) }),
          }}
        />
      )}
    </div>
  )
}
