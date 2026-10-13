import { useQuery } from "@tanstack/react-query"
import {
  createFileRoute,
  stripSearchParams,
  useNavigate,
} from "@tanstack/react-router"
import { ShoppingCart } from "lucide-react"
import { z } from "zod"

import { columns } from "@/components/Backoffice/Orders/columns"
import { DataTable } from "@/components/Common/DataTable"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ADMIN_PAGE_SIZE, pageTitle } from "@/config"
import { ORDER_TABS, type OrderTab } from "@/lib/orders"
import { adminOrdersQueryOptions } from "@/lib/queries/orders"

const ordersSearch = z.object({
  tab: z
    .enum(["in_progress", "completed", "cancelled", "placed", "draft"])
    .catch("in_progress")
    .default("in_progress"),
  page: z.number().int().positive().catch(1).default(1),
})

export const Route = createFileRoute("/admin/orders/")({
  component: Orders,
  search: {
    middlewares: [stripSearchParams({ tab: "in_progress", page: 1 })],
  },
  validateSearch: ordersSearch,
  head: () => ({
    meta: [{ title: pageTitle("Orders") }],
  }),
})

function Orders() {
  const { tab, page } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const states = ORDER_TABS.find((t) => t.value === tab)?.states ?? []
  const { data, isPending } = useQuery(
    adminOrdersQueryOptions({ states, page, pageSize: ADMIN_PAGE_SIZE }),
  )
  const orders = data?.data ?? []

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Orders</h1>
        <p className="text-muted-foreground">
          Review and fulfil customer orders
        </p>
      </div>

      <Tabs
        value={tab}
        onValueChange={(value) =>
          navigate({ search: { tab: value as OrderTab, page: 1 } })
        }
      >
        <div className="overflow-x-auto">
          <TabsList>
            {ORDER_TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {/* One panel for the active tab: the table renders once */}
        <TabsContent value={tab} className="mt-4">
          {isPending ? (
            <Skeleton className="h-32 w-full" />
          ) : orders.length === 0 && page === 1 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="mb-4 rounded-full bg-muted p-4">
                <ShoppingCart className="h-8 w-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold">No orders here yet</h3>
            </div>
          ) : (
            <DataTable
              columns={columns}
              data={orders}
              pagination={{
                page,
                pageSize: ADMIN_PAGE_SIZE,
                total: data?.count ?? 0,
                onPageChange: (p) =>
                  navigate({ search: (prev) => ({ ...prev, page: p }) }),
              }}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
