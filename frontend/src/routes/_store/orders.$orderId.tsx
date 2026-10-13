import { useSuspenseQuery } from "@tanstack/react-query"
import {
  createFileRoute,
  Link,
  notFound,
  useNavigate,
} from "@tanstack/react-router"
import { AxiosError } from "axios"
import { ArrowLeft, CheckCircle2 } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { z } from "zod"

import NotFound from "@/components/Common/NotFound"
import { OrderItemsTable } from "@/components/Orders/OrderItemsTable"
import { OrderSummaryHeader } from "@/components/Orders/OrderSummaryHeader"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { pageTitle } from "@/config"
import { requireUser } from "@/lib/auth"
import { myOrderQueryOptions } from "@/lib/queries/orders"

const orderSearch = z.object({
  placed: z.boolean().optional().catch(undefined),
})

export const Route = createFileRoute("/_store/orders/$orderId")({
  component: OrderDetail,
  notFoundComponent: NotFound,
  beforeLoad: ({ location }) => requireUser(location),
  validateSearch: orderSearch,
  loader: async ({ context, params }) => {
    if (!z.uuid().safeParse(params.orderId).success) throw notFound()
    try {
      return await context.queryClient.ensureQueryData(
        myOrderQueryOptions(params.orderId),
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
  const { placed } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const { data: order } = useSuspenseQuery(myOrderQueryOptions(orderId))
  // Kept in state so stripping the param doesn't hide the alert
  const [showPlaced] = useState(placed === true)
  const alertRef = useRef<HTMLDivElement>(null)

  // biome-ignore lint/correctness/useExhaustiveDependencies: runs once per order
  useEffect(() => {
    if (!placed) return
    alertRef.current?.focus()
    navigate({ search: {}, replace: true })
  }, [orderId])

  return (
    <div className="flex flex-col gap-6">
      <Button variant="ghost" className="-ml-3 w-fit" asChild>
        <Link to="/orders">
          <ArrowLeft />
          Back to my orders
        </Link>
      </Button>
      {showPlaced && (
        <Alert ref={alertRef} tabIndex={-1} data-testid="order-placed-alert">
          <CheckCircle2 aria-hidden />
          <AlertDescription className="text-foreground">
            Order placed! We've emailed you a summary.
          </AlertDescription>
        </Alert>
      )}
      <OrderSummaryHeader order={order} />
      <OrderItemsTable order={order} />
    </div>
  )
}
