import type { OrderPublic } from "@/client"
import { formatDate } from "@/lib/format"

export function OrderTimeline({ order }: { order: OrderPublic }) {
  const rows = [
    ["Created", order.created_at],
    ["Placed", order.placed_at],
    ["Completed", order.completed_at],
    ["Cancelled", order.cancelled_at],
  ] as const
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      {rows.map(([label, value]) =>
        value ? (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd>{formatDate(value)}</dd>
          </div>
        ) : null,
      )}
    </dl>
  )
}
