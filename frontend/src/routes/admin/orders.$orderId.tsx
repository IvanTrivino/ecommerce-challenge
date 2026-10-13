import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, Link, notFound } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { ArrowLeft } from "lucide-react"
import { z } from "zod"

import { OrderActionButton } from "@/components/Backoffice/Orders/OrderActionButton"
import NotFound from "@/components/Common/NotFound"
import { OrderItemsTable } from "@/components/Orders/OrderItemsTable"
import { OrderSummaryHeader } from "@/components/Orders/OrderSummaryHeader"
import { OrderTimeline } from "@/components/Orders/OrderTimeline"
import { Button } from "@/components/ui/button"
import { pageTitle } from "@/config"
import { adminOrderQueryOptions } from "@/lib/queries/orders"

export const Route = createFileRoute("/admin/orders/$orderId")({
  component: OrderDetail,
  notFoundComponent: NotFound,
  loader: async ({ context, params }) => {
    if (!z.uuid().safeParse(params.orderId).success) throw notFound()
    try {
      return await context.queryClient.ensureQueryData(
        adminOrderQueryOptions(params.orderId),
      )
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        throw notFound()
      }
      throw error
    }
  },
  head: ({ loaderData }) => ({
    meta: [{ title: pageTitle(`Order #${loaderData?.number ?? ""}`) }],
  }),
})

function OrderDetail() {
  const { orderId } = Route.useParams()
  const { data: order } = useSuspenseQuery(adminOrderQueryOptions(orderId))

  return (
    <div className="flex flex-col gap-6">
      <Button variant="ghost" className="-ml-3 w-fit" asChild>
        <Link to="/admin/orders">
          <ArrowLeft />
          Back to orders
        </Link>
      </Button>
      <OrderSummaryHeader
        order={order}
        actions={
          <>
            <OrderActionButton order={order} kind="cancel" />
            <OrderActionButton order={order} kind="complete" />
          </>
        }
      />
      <p className="text-sm">
        <span className="text-muted-foreground">Customer </span>
        <span data-testid="order-customer">{order.user_email}</span>
      </p>
      <OrderTimeline order={order} />
      <OrderItemsTable order={order} />
    </div>
  )
}
