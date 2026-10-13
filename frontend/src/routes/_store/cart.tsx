import { createFileRoute, Link } from "@tanstack/react-router"
import { ShoppingCart } from "lucide-react"

import { CartLine } from "@/components/Store/Cart/CartLine"
import { CartSummary } from "@/components/Store/Cart/CartSummary"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { pageTitle } from "@/config"
import { useCart } from "@/hooks/useCart"
import { requireUser } from "@/lib/auth"

export const Route = createFileRoute("/_store/cart")({
  component: Cart,
  beforeLoad: ({ location }) => requireUser(location),
  head: () => ({
    meta: [{ title: pageTitle("Cart") }],
  }),
})

function Cart() {
  const { data: cart } = useCart()

  if (!cart) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (cart.items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="mb-4 rounded-full bg-muted p-4">
          <ShoppingCart className="h-8 w-8 text-muted-foreground" />
        </div>
        <h1 className="text-lg font-semibold">Your cart is empty</h1>
        <p className="mb-4 text-muted-foreground">
          Add some products to get started
        </p>
        <Button asChild>
          <Link to="/">Continue shopping</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">Cart</h1>
      <div className="grid gap-8 lg:grid-cols-[1fr_20rem] lg:items-start">
        <ul
          className="divide-y rounded-lg border px-4"
          data-testid="cart-lines"
        >
          {cart.items.map((item) => (
            <CartLine key={item.id} item={item} />
          ))}
        </ul>
        <CartSummary cart={cart} />
      </div>
    </div>
  )
}
