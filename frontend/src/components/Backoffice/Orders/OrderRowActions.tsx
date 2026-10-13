import { Link } from "@tanstack/react-router"

import type { OrderSummaryPublic } from "@/client"
import { OrderActionButton } from "@/components/Backoffice/Orders/OrderActionButton"
import { Button } from "@/components/ui/button"

export function OrderRowActions({ order }: { order: OrderSummaryPublic }) {
  return (
    <div className="flex gap-2">
      <Button variant="ghost" size="sm" asChild>
        <Link
          to="/admin/orders/$orderId"
          params={{ orderId: order.id }}
          aria-label={`View order ${order.number}`}
          data-testid="view-order"
        >
          View
        </Link>
      </Button>
      <OrderActionButton order={order} kind="cancel" size="sm" />
      <OrderActionButton order={order} kind="complete" size="sm" />
    </div>
  )
}
