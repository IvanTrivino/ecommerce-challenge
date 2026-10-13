import { Link } from "@tanstack/react-router"
import { Trash2 } from "lucide-react"

import type { CartItemPublic } from "@/client"
import { QuantityStepper } from "@/components/Store/Cart/QuantityStepper"
import { ProductImage } from "@/components/Store/ProductImage"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { useCartMutations } from "@/hooks/useCart"
import { formatPrice } from "@/lib/format"
import { MAX_QUANTITY_PER_ITEM } from "@/lib/orders"
import { cn } from "@/lib/utils"

export function CartLine({ item }: { item: CartItemPublic }) {
  const { update, remove } = useCartMutations()
  const busy = update.isPending || remove.isPending
  // A line already above the stock can still be lowered, but not raised
  const max = Math.max(
    item.quantity,
    Math.min(item.available_stock, MAX_QUANTITY_PER_ITEM),
  )

  return (
    <li
      className={cn("flex flex-col gap-3 py-4", busy && "opacity-60")}
      aria-busy={busy}
      data-testid="cart-line"
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <div className="size-16 shrink-0 overflow-hidden rounded-md border">
            <ProductImage key={item.image_url} src={item.image_url} alt="" />
          </div>
          <div className="min-w-0">
            <Link
              to="/products/$productId"
              params={{ productId: item.product_id }}
              className="line-clamp-2 font-medium break-words hover:underline"
            >
              {item.name}
            </Link>
            <p className="font-mono text-xs text-muted-foreground">
              {item.sku}
            </p>
            <p className="text-sm text-muted-foreground">
              {formatPrice(item.unit_price)}
            </p>
          </div>
        </div>
        <div className="flex items-center justify-between gap-4 md:justify-end">
          <QuantityStepper
            value={item.quantity}
            max={max}
            label={item.name}
            onChange={(quantity) => update.mutate({ id: item.id, quantity })}
          />
          <span
            className={cn(
              "w-24 text-right font-medium tabular-nums",
              !item.available && "text-muted-foreground line-through",
            )}
          >
            {formatPrice(item.line_total)}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Remove ${item.name}`}
            data-testid="remove-line"
            disabled={busy}
            onClick={() => remove.mutate(item.id)}
          >
            <Trash2 aria-hidden />
          </Button>
        </div>
      </div>
      {!item.available && (
        <Alert variant="destructive">
          <AlertDescription className="text-destructive">
            {item.available_stock === 0
              ? "No longer available"
              : `Only ${item.available_stock} left — lower the quantity`}
          </AlertDescription>
        </Alert>
      )}
    </li>
  )
}
