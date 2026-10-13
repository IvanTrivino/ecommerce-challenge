import { Link } from "@tanstack/react-router"

import type { CartPublic } from "@/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { formatPrice, formatWeight } from "@/lib/format"

export function CartSummary({ cart }: { cart: CartPublic }) {
  return (
    <Card className="lg:sticky lg:top-24">
      <CardHeader>
        <CardTitle>Summary</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl aria-live="polite" className="flex flex-col gap-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Items</dt>
            <dd data-testid="cart-items">{cart.item_count}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Total weight</dt>
            <dd>{formatWeight(cart.total_weight)}</dd>
          </div>
          <div className="flex justify-between text-base font-semibold">
            <dt>Total</dt>
            <dd data-testid="cart-total">{formatPrice(cart.total_price)}</dd>
          </div>
        </dl>
        {cart.can_place ? (
          <Button asChild data-testid="checkout-button">
            <Link to="/checkout">Checkout</Link>
          </Button>
        ) : (
          <>
            <Button disabled data-testid="checkout-button">
              Checkout
            </Button>
            <p className="text-sm text-muted-foreground">
              Fix the items marked above to continue
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
