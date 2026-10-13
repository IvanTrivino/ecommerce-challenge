import { Check, type LucideIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { OrderState } from "@/lib/orders"

type BadgeVariant = "default" | "secondary" | "destructive" | "outline"

const STATES: Record<
  OrderState,
  { label: string; variant: BadgeVariant; icon?: LucideIcon }
> = {
  draft: { label: "Draft", variant: "outline" },
  in_progress: { label: "In progress", variant: "default" },
  completed: { label: "Completed", variant: "secondary", icon: Check },
  cancelled: { label: "Cancelled", variant: "destructive" },
}

export function OrderStateBadge({ state }: { state: OrderState }) {
  const { label, variant, icon: Icon } = STATES[state]
  return (
    <Badge variant={variant} data-testid="order-state">
      {Icon ? <Icon aria-hidden /> : null}
      {label}
    </Badge>
  )
}
