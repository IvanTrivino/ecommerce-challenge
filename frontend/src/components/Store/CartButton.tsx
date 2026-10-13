import { Link } from "@tanstack/react-router"
import { ShoppingCart } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useCart } from "@/hooks/useCart"

export function CartButton() {
  const { data } = useCart()
  const count = data?.item_count ?? 0
  const badge = count > 99 ? "99+" : String(count)

  return (
    <Button variant="ghost" size="icon" className="relative" asChild>
      <Link
        to="/cart"
        aria-label={`Cart, ${count} ${count === 1 ? "item" : "items"}`}
        data-testid="cart-button"
      >
        <ShoppingCart />
        {count > 0 && (
          <span
            aria-hidden
            className="absolute -right-1 -top-1 min-w-5 rounded-full bg-primary px-1 text-center text-[11px] font-semibold leading-5 text-primary-foreground"
            data-testid="cart-count"
          >
            {badge}
          </span>
        )}
      </Link>
    </Button>
  )
}
