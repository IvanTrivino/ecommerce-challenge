import { useQuery } from "@tanstack/react-query"
import {
  createFileRoute,
  Link,
  stripSearchParams,
  useNavigate,
} from "@tanstack/react-router"
import { Package } from "lucide-react"
import { z } from "zod"

import { OrderStateBadge } from "@/components/Orders/OrderStateBadge"
import { PaginationBar } from "@/components/Store/PaginationBar"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { pageTitle } from "@/config"
import { requireUser } from "@/lib/auth"
import { formatDate, formatPrice } from "@/lib/format"
import { MY_ORDERS_PAGE_SIZE } from "@/lib/orders"
import { myOrdersQueryOptions } from "@/lib/queries/orders"

const ordersSearch = z.object({
  page: z.number().int().positive().catch(1).default(1),
})

export const Route = createFileRoute("/_store/orders/")({
  component: MyOrders,
  beforeLoad: ({ location }) => requireUser(location),
  search: { middlewares: [stripSearchParams({ page: 1 })] },
  validateSearch: ordersSearch,
  head: () => ({
    meta: [{ title: pageTitle("My orders") }],
  }),
})

function MyOrders() {
  const { page } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const { data, isPending } = useQuery(
    myOrdersQueryOptions(page, MY_ORDERS_PAGE_SIZE),
  )
  const orders = data?.data ?? []

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">My orders</h1>
      {isPending ? (
        <Skeleton className="h-32 w-full" />
      ) : orders.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="mb-4 rounded-full bg-muted p-4">
            <Package className="h-8 w-8 text-muted-foreground" />
          </div>
          <p className="mb-4 text-muted-foreground">
            You haven't placed any orders yet.
          </p>
          <Button asChild>
            <Link to="/">Start shopping</Link>
          </Button>
        </div>
      ) : (
        <ul className="divide-y rounded-lg border" data-testid="my-orders">
          {orders.map((order) => (
            <li key={order.id}>
              <Link
                to="/orders/$orderId"
                params={{ orderId: order.id }}
                className="flex flex-wrap items-center gap-x-6 gap-y-1 px-4 py-3 hover:bg-accent/50"
                data-testid="my-order"
              >
                <span className="font-mono font-medium">#{order.number}</span>
                <span className="text-sm text-muted-foreground">
                  {order.placed_at ? formatDate(order.placed_at) : "—"}
                </span>
                <span className="text-sm text-muted-foreground">
                  {order.item_count} {order.item_count === 1 ? "item" : "items"}
                </span>
                <span className="ml-auto flex items-center gap-4">
                  <span className="font-medium tabular-nums">
                    {order.total_price ? formatPrice(order.total_price) : "—"}
                  </span>
                  <OrderStateBadge state={order.state} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <PaginationBar
        page={page}
        pageSize={MY_ORDERS_PAGE_SIZE}
        total={data?.count ?? 0}
        onPageChange={(p) =>
          navigate({ search: (prev) => ({ ...prev, page: p }) })
        }
      />
    </div>
  )
}
