import {
  useMutation,
  useQueryClient,
  useSuspenseQuery,
} from "@tanstack/react-query"
import {
  createFileRoute,
  Link,
  redirect,
  useNavigate,
} from "@tanstack/react-router"
import { useState } from "react"

import { CartService } from "@/client"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { pageTitle } from "@/config"
import useCustomToast from "@/hooks/useCustomToast"
import { requireUser } from "@/lib/auth"
import { formatPrice, formatWeight } from "@/lib/format"
import { apiError } from "@/lib/orders"
import { cartKeys, cartQueryOptions } from "@/lib/queries/cart"
import { orderKeys } from "@/lib/queries/orders"
import { productKeys } from "@/lib/queries/products"

export const Route = createFileRoute("/_store/checkout")({
  component: Checkout,
  beforeLoad: ({ location }) => requireUser(location),
  loader: async ({ context }) => {
    const cart = await context.queryClient.fetchQuery({
      ...cartQueryOptions,
      staleTime: 0,
    })
    if (!cart.can_place) throw redirect({ to: "/cart" })
    return cart
  },
  head: () => ({
    meta: [{ title: pageTitle("Checkout") }],
  }),
})

type PlaceError = { tone: "warning" | "error"; text: string; retry?: boolean }

const WARNING_CLASSES =
  "border-amber-500/50 text-amber-700 dark:text-amber-400 [&_[data-slot=alert-description]]:text-amber-700 dark:[&_[data-slot=alert-description]]:text-amber-400"

function Checkout() {
  const { data: cart } = useSuspenseQuery(cartQueryOptions)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { showErrorToast } = useCustomToast()
  const [placeError, setPlaceError] = useState<PlaceError | null>(null)

  const place = useMutation({
    mutationFn: async () =>
      (
        await CartService.placeOrder({
          // The loader guarantees a placeable cart, which always has an id
          body: {
            order_id: cart.id as string,
            expected_total: cart.total_price,
          },
        })
      ).data,
    onMutate: () => setPlaceError(null),
    onSuccess: (order) => {
      queryClient.invalidateQueries({ queryKey: cartKeys.all })
      queryClient.invalidateQueries({ queryKey: orderKeys.all })
      queryClient.invalidateQueries({ queryKey: productKeys.all })
      navigate({
        to: "/orders/$orderId",
        params: { orderId: order.id },
        search: { placed: true },
      })
    },
    onError: async (err) => {
      const { status, detail } = apiError(err)
      if (status === 409 && detail.startsWith("Prices changed")) {
        await queryClient.refetchQueries({ queryKey: cartKeys.all })
        setPlaceError({
          tone: "warning",
          text: "Some prices changed. Please review the new total before placing your order.",
        })
      } else if (status === 409) {
        await queryClient.refetchQueries({ queryKey: cartKeys.all })
        showErrorToast(detail)
        navigate({ to: "/cart" })
      } else if (status === 402) {
        setPlaceError({ tone: "error", text: "Your payment was declined." })
      } else {
        setPlaceError({ tone: "error", text: detail, retry: true })
      }
    },
  })

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">Checkout</h1>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Item</TableHead>
            <TableHead className="text-right">Qty</TableHead>
            <TableHead className="text-right">Unit price</TableHead>
            <TableHead className="text-right">Total</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {cart.items.map((item) => (
            <TableRow key={item.id} data-testid="checkout-line">
              <TableCell className="whitespace-normal break-words font-medium">
                {item.name}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {item.quantity}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatPrice(item.unit_price)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatPrice(item.line_total)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell colSpan={3}>Total weight</TableCell>
            <TableCell className="text-right tabular-nums">
              {formatWeight(cart.total_weight)}
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell colSpan={3} className="font-semibold">
              Total
            </TableCell>
            <TableCell
              className="text-right font-semibold tabular-nums"
              data-testid="checkout-total"
            >
              {formatPrice(cart.total_price)}
            </TableCell>
          </TableRow>
        </TableFooter>
      </Table>
      <p className="text-sm text-muted-foreground">
        Payment is simulated, no card is needed.
      </p>
      {placeError && (
        <Alert
          variant={placeError.tone === "error" ? "destructive" : "default"}
          className={
            placeError.tone === "warning" ? WARNING_CLASSES : undefined
          }
          data-testid="place-error"
        >
          <AlertDescription className="flex flex-wrap items-center gap-3 text-inherit">
            {placeError.text}
            {placeError.retry && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => place.mutate()}
              >
                Try again
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}
      <div className="flex flex-wrap gap-3">
        <Button variant="outline" asChild>
          <Link to="/cart">Back to cart</Link>
        </Button>
        <LoadingButton
          loading={place.isPending}
          onClick={() => place.mutate()}
          data-testid="place-order"
        >
          Place order
        </LoadingButton>
      </div>
    </div>
  )
}
