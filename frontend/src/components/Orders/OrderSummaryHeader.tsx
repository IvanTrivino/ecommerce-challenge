import type { ReactNode } from "react"

import type { OrderPublic } from "@/client"
import { OrderStateBadge } from "@/components/Orders/OrderStateBadge"
import { formatDate } from "@/lib/format"

export function OrderSummaryHeader({
  order,
  actions,
}: {
  order: OrderPublic
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">
            Order #{order.number}
          </h1>
          <OrderStateBadge state={order.state} />
        </div>
        <p className="text-sm text-muted-foreground">
          {order.placed_at
            ? `Placed ${formatDate(order.placed_at)}`
            : "Not placed"}
        </p>
        {order.payment_reference ? (
          <p className="text-sm text-muted-foreground">
            Payment reference{" "}
            <span className="font-mono">{order.payment_reference}</span>
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  )
}
