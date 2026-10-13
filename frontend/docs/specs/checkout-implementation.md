# Implementation Plan: Cart, Checkout and Orders (frontend)

This plan is for the engineer or model implementing the frontend part of
[`checkout.md`](./checkout.md) (the **spec**). The spec decides *what* to build. This document
decides *how* and *in what order*. If the two disagree, the spec wins: stop and ask rather than
guess.

Requirement IDs (`FR-x`, `NFR-x`, `AC-x`) refer to the frontend spec. "Backend spec" means
[`backend/docs/specs/checkout.md`](../../../backend/docs/specs/checkout.md), and "backend plan"
means [`backend/docs/specs/checkout-implementation.md`](../../../backend/docs/specs/checkout-implementation.md).
**Appendix B of the backend plan is the API contract you code against.** Keep it open.

---

## 0. Before you start

### 0.1 Prerequisite: the backend

Steps 1–6 need **backend plan Step 10** merged (all endpoints exist, and the client is
regenerated). Step 7 (Playwright) also needs the Celery worker and beat running, because one test
reads the order email from Mailpit.

Check:

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
grep -c "readCart\|addCartItem\|placeOrder\|readMyOrders\|cancelOrder" frontend/src/client/sdk.gen.ts   # >= 5
```

If the client wasn't regenerated, run `bash scripts/generate-client.sh` from the repo root. If a
method name differs from the backend plan's Appendix B, **use the generated name** and note it in
your PR.

### 0.2 Read these files first

| File | Why |
|---|---|
| `frontend/docs/specs/storefront-backoffice-implementation.md` §0.2–0.4 | **Commands and codebase rules. They apply unchanged**: Bun via `npx bun`, Biome, strict TS, shadcn CLI for `ui/`, never edit `src/client/**` or `routeTree.gen.ts`, mutation conventions, commit format |
| `src/routes/_store.tsx`, `src/routes/_store/products.$productId.tsx`, `src/routes/_store/account.tsx` | Storefront layout, loader + `notFound` pattern, `requireUser` guard |
| `src/routes/admin.tsx`, `src/routes/admin/imports.index.tsx`, `src/routes/admin/imports.$importId.tsx` | Admin page layout, `validateSearch` with zod + `stripSearchParams`, list + detail route pair |
| `src/components/Store/ProductCard.tsx`, `StoreHeader.tsx`, `StoreUserMenu.tsx`, `StockBadge.tsx`, `PaginationBar.tsx` | Components you change or reuse |
| `src/components/Common/DataTable.tsx`, `src/components/Backoffice/Imports/columns.tsx`, `ImportStatusBadge.tsx` | Table with server pagination (TanStack Table **v9**), column style, badge style |
| `src/components/Backoffice/Products/DeleteProduct.tsx` | Confirm-dialog + mutation pattern (`LoadingButton`, `handleError.bind(showErrorToast)`, invalidate in `onSettled`) |
| `src/lib/queries/*.ts` | Query key factories and `queryOptions` style |
| `src/lib/auth.ts`, `src/hooks/useAuth.ts`, `src/lib/apiErrors.ts` | `isLoggedIn`, `subscribeAuth`, `requireUser`, `clearSession`, `isProtected` |
| `src/utils.ts`, `src/hooks/useCustomToast.ts`, `src/lib/format.ts` | `extractErrorMessage`, `handleError`, toasts, `formatPrice`, `formatWeight`, `formatDate` |
| `src/config.ts` | `pageTitle`, `ADMIN_PAGE_SIZE`, `LOW_STOCK_THRESHOLD` |
| `tests/utils/api.ts`, `tests/utils/user.ts`, `tests/utils/mailpit.ts`, `tests/utils/random.ts` | Playwright helpers: admin API client, log in and out, reading emails |
| `tests/storefront.spec.ts`, `tests/responsive-keyboard.spec.ts` | Style, and the tests your ProductCard change affects |

### 0.3 Existing behaviour that affects this work

1. **Money and weights are strings** in responses (`"19.99"`). Inputs accept `number | string`.
   Display with `formatPrice` / `formatWeight`. **Never add prices up in the UI** (spec NFR-3).
   Every total comes from the API.
2. **`ProductCard` is a single `<Link>`.** A `<button>` inside an `<a>` is invalid HTML and
   breaks keyboard and click handling. Step 3 restructures the card. Three existing tests rely on
   the card's shape (`tests/responsive-keyboard.spec.ts` focuses the card element itself, line
   ~190), and Step 3 says how to update them.
3. **The cart query only makes sense when logged in.** Anonymous calls to `/cart` return 401, and
   `handleApiError` treats a 401 as an invalid session: it clears the token and may redirect.
   **Never** run cart queries for visitors. Gate them on `isLoggedIn()` /
   `useAuth().loggedIn`.
4. **`isProtected()` in `src/lib/apiErrors.ts`** decides where to redirect after a session
   expires. Add `/cart`, `/checkout` and `/orders`, or a user whose session expires on those pages
   is left on a broken page.
5. **`clearSession()`** only removes `["currentUser"]`. The cart and orders of the previous user
   would survive a logout, and the next user to log in on the same tab would see them. Step 1
   fixes this (spec FR-1.4).
6. **Login already supports `?redirect=`** (`src/routes/login.tsx`, `isSafeRedirect`).
   `requireUser(location)` sets it. "+ Add" for visitors uses the same mechanism.
7. **Superusers land on `/admin` after login** (`homeFor`). With `?redirect=`, they go to the
   redirect instead. Superusers can use the cart like anyone else.
8. **Playwright's default storage state is the superuser** (`tests/auth.setup.ts`). Customer
   flows must use a fresh context (`browser.newContext({ storageState: { cookies: [], origins: [] } })`)
   and a fresh customer created through the API. Never share a customer between tests: their cart
   would leak (one Draft per user).
9. **Tests run `fullyParallel`.** Every test creates its **own** category and products, so stock
   and price changes in one test never affect another.
10. **`DataTable` pagination is server-side** (`pagination` prop). Rows are already paged by the
    API.
11. **Disabled buttons swallow pointer events**, so a Radix tooltip on a disabled button never
    opens. Wrap the disabled button in a `<span tabIndex={0}>` that carries the tooltip trigger
    (Step 5).

---

## Step 1: Queries, hooks and session plumbing

**Spec:** FR-1

### 1.1 `src/lib/queries/cart.ts` (new)

```ts
import { queryOptions } from "@tanstack/react-query"

import { CartService } from "@/client"

export const cartKeys = { all: ["cart"] as const }

export const cartQueryOptions = queryOptions({
  queryKey: cartKeys.all,
  queryFn: async () => (await CartService.readCart()).data,
  staleTime: 30_000,
})
```

Components must spread it with `enabled: loggedIn` (§0.3.3). Don't put `enabled` in the shared
options: `fetchQuery` in loaders ignores it anyway.

### 1.2 `src/lib/queries/orders.ts` (new)

```ts
export const orderKeys = {
  all: ["orders"] as const,
  mine: (page: number) => ["orders", "mine", page] as const,
  myDetail: (id: string) => ["orders", "mine", "detail", id] as const,
  admin: (states: OrderState[], page: number) => ["orders", "admin", states, page] as const,
  adminDetail: (id: string) => ["orders", "admin", "detail", id] as const,
}
```

Add `myOrdersQueryOptions(page, pageSize)`, `myOrderQueryOptions(id)`,
`adminOrdersQueryOptions({ states, page, pageSize })` (with `placeholderData: keepPreviousData`
and `refetchOnWindowFocus: true`), and `adminOrderQueryOptions(id)`, following
`lib/queries/productImports.ts`. `OrderState` is the generated union type. Import it from
`@/client`, and if the generator inlined it, derive it as `OrderPublic["state"]`.

### 1.3 `src/lib/orders.ts` (new): constants and helpers

```ts
export const MAX_QUANTITY_PER_ITEM = 99   // backend MAX_QUANTITY_PER_ITEM
export const MY_ORDERS_PAGE_SIZE = 10

export type OrderTab = "in_progress" | "completed" | "cancelled" | "placed" | "draft"
export const ORDER_TABS: { value: OrderTab; label: string; states: OrderState[] }[] = [
  { value: "in_progress", label: "In progress", states: ["in_progress"] },
  { value: "completed", label: "Completed", states: ["completed"] },
  { value: "cancelled", label: "Cancelled", states: ["cancelled"] },
  { value: "placed", label: "All placed", states: ["in_progress", "completed", "cancelled"] },
  { value: "draft", label: "Drafts", states: ["draft"] },
]

export const canAct = (o: { state: OrderState }) => o.state === "in_progress"

// The status code and detail of an API error, for flows that branch on them
export function apiError(err: unknown): { status?: number; detail: string } { ... }
```

`apiError` uses `AxiosError` and `extractErrorMessage` from `@/utils`. Put it here rather than in
`utils.ts`: only order flows need to branch on the status code.

### 1.4 `src/hooks/useCart.ts` (new)

```ts
export function useCart() {
  const { loggedIn } = useAuth()
  return useQuery({ ...cartQueryOptions, enabled: loggedIn })
}

export function useCartMutations() {
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()
  const setCart = (cart: CartPublic) => queryClient.setQueryData(cartKeys.all, cart)
  const onError = (err: Error) => {
    showErrorToast(extractErrorMessage(err))
    // the server may know better (stock changed, line gone): resync
    queryClient.invalidateQueries({ queryKey: cartKeys.all })
  }
  const update = useMutation({
    mutationFn: async ({ id, quantity }: { id: string; quantity: number }) =>
      (await CartService.updateCartItem({ path: { item_id: id }, body: { quantity } })).data,
    onSuccess: setCart,
    onError,
  })
  const remove = useMutation({ /* removeCartItem, same shape */ })
  return { update, remove }
}
```

Mutations **set** the returned `CartPublic` into the cache. They don't invalidate on success,
because the server's response is already the new cart (spec FR-1.1). No optimistic updates (spec
non-goals).

### 1.5 `src/hooks/useAddToCart.ts` (new)

```ts
export function useAddToCart() {
  const { loggedIn } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const mutation = useMutation({
    mutationFn: async (vars: { productId: string; quantity?: number; name: string }) =>
      (await CartService.addCartItem({
        body: { product_id: vars.productId, quantity: vars.quantity ?? 1 },
      })).data,
    onSuccess: (cart, vars) => {
      queryClient.setQueryData(cartKeys.all, cart)
      toast.success("Added to cart", {
        description: vars.name,
        action: { label: "View cart", onClick: () => navigate({ to: "/cart" }) },
      })
    },
    onError: handleError.bind(showErrorToast),
  })

  const add = (vars: { productId: string; quantity?: number; name: string }) => {
    if (!loggedIn) {
      const { pathname, search } = window.location
      navigate({ to: "/login", search: { redirect: pathname + search } })
      return
    }
    mutation.mutate(vars)
  }

  return { add, isPending: mutation.isPending, pendingId: mutation.variables?.productId }
}
```

`toast` comes straight from `sonner`, because `useCustomToast` has no action button. Every product
card calls this hook, so a grid of 12 cards has 12 mutation instances. Each one tracks its own
`isPending`, which is what the card needs.

### 1.6 Session plumbing

- `src/lib/auth.ts` → `clearSession()` also calls
  `queryClient.removeQueries({ queryKey: ["cart"] })` and
  `queryClient.removeQueries({ queryKey: ["orders"] })`. Use the literal keys: importing
  `cartKeys` from `lib/queries/cart.ts` would create an import cycle through the client, so check
  for one before you try it.
- `src/lib/apiErrors.ts` → `isProtected` also matches `/cart`, `/checkout` and paths starting
  with `/orders` (§0.3.4).

### 1.7 `src/lib/format.ts`

`formatWeight` already exists. Add:

```ts
export const orderNumber = (id: string) => id.replaceAll("-", "").slice(0, 8).toUpperCase()
```

Prefer the API's `number` field wherever you have an order object. `orderNumber` is only for
places that have just an id, such as toasts after a mutation.

**Done when:** `build`, `lint` and `tsc --noEmit -p frontend` pass. There's no UI yet.

Commit: `(feat): Add cart and order queries`

---

## Step 2: Shared order components

**Spec:** FR-5.4, FR-5.2, FR-6.4

All in `src/components/Orders/` (new folder, shared by the storefront and the backoffice).

### 2.1 `OrderStateBadge.tsx`

```tsx
const STATES: Record<OrderState, { label: string; variant: BadgeVariant; icon?: LucideIcon }> = {
  draft: { label: "Draft", variant: "outline" },
  in_progress: { label: "In progress", variant: "default" },
  completed: { label: "Completed", variant: "secondary", icon: Check },
  cancelled: { label: "Cancelled", variant: "destructive" },
}

export function OrderStateBadge({ state }: { state: OrderState }) {
  // <Badge variant=… data-testid="order-state">{icon}{label}</Badge>
}
```

### 2.2 `OrderItemsTable.tsx`

Props: `{ order: OrderPublic }`. A plain `ui/table` with these columns:

- Item (name, plus the SKU in `font-mono text-xs text-muted-foreground`)
- Qty
- Unit price
- Total

A `<TableFooter>` holds two rows: Total weight (`formatWeight(order.total_weight)`) and **Total**
(`formatPrice(order.total_price)`). For a Draft (admin only), the price fields are null: show
"—" and skip the footer. Right-align the number columns with `tabular-nums`.

### 2.3 `OrderSummaryHeader.tsx`

Props: `{ order: OrderPublic; actions?: ReactNode }`. Renders:

- `<h1>Order #{order.number}</h1>`
- the `OrderStateBadge`
- `Placed {formatDate(order.placed_at)}` (or "Not placed" for a Draft)
- `Payment reference {order.payment_reference}` when there is one
- `actions` aligned right. Below `sm`, they stack under the title.

### 2.4 `OrderTimeline.tsx` (admin detail only)

A `<dl>` of Created, Placed, Completed and Cancelled, with `formatDate`. Rows whose timestamp is
null are skipped.

**Done when:** build and lint pass.

Commit: `(feat): Add shared order components`

---

## Step 3: "+ Add" on the storefront and the header cart button

**Spec:** FR-2

### 3.1 `src/components/Store/ProductCard.tsx`: restructure

Target markup: a "stretched link". The whole card stays clickable, and the button is a sibling of
the link, not a child:

```tsx
<article
  data-testid="product-card"
  className="group relative flex flex-col overflow-hidden rounded-lg border bg-card transition-shadow hover:shadow-md has-[a:focus-visible]:ring-[3px] has-[a:focus-visible]:ring-ring/50"
>
  <ProductImage key={product.image_url} src={product.image_url} alt="" />
  <div className="flex flex-1 flex-col gap-2 p-4">
    <span className="text-xs text-muted-foreground">{categoryName(product.category_uuid)}</span>
    <h3 className="line-clamp-2 font-medium leading-snug group-hover:underline">
      <Link
        to="/products/$productId"
        params={{ productId: product.id }}
        className="outline-none after:absolute after:inset-0 after:content-['']"
      >
        {product.name}
      </Link>
    </h3>
    <div className="mt-auto flex items-center justify-between gap-2 pt-2">
      <span className="font-semibold">{formatPrice(product.price)}</span>
      <StockBadge stock={product.stock ?? 0} />
    </div>
    <AddToCartButton product={product} className="relative z-10 mt-2 w-full" />
  </div>
</article>
```

- `after:absolute after:inset-0` on the link covers the card, and `relative z-10` lifts the
  button above that overlay. Check by hand that clicking the image, the category and the empty
  space all navigate, and that clicking the button only adds.
- The focus ring moves from the card to `has-[a:focus-visible]`, so keyboard users still see the
  whole card highlighted.

### 3.2 `src/components/Store/AddToCartButton.tsx` (new)

```tsx
export function AddToCartButton({ product, quantity = 1, className, size = "sm" }: Props) {
  const { add, isPending } = useAddToCart()
  const soldOut = (product.stock ?? 0) <= 0
  return (
    <LoadingButton
      size={size}
      className={className}
      loading={isPending}
      disabled={soldOut}
      onClick={() => add({ productId: product.id, quantity, name: product.name })}
      aria-label={soldOut ? `${product.name} is sold out` : `Add ${product.name} to cart`}
      data-testid="add-to-cart"
    >
      {soldOut ? "Sold out" : <><Plus /> Add</>}
    </LoadingButton>
  )
}
```

The product page (§3.3) passes a different label through a `children` override. Make the label
part of the props, `label?: string` with default `"Add"`, rather than duplicating the component.

### 3.3 Product page (`src/routes/_store/products.$productId.tsx`)

Below the price and stock row, add a small form:

- `<Label htmlFor="quantity">Quantity</Label>`
- `<Input id="quantity" type="number" min={1} max={Math.min(stock, 99)} …>`, `w-20`, holding
  local state that is clamped on blur
- `<AddToCartButton product={product} quantity={qty} label="Add to cart" size="default" />`

Hide the quantity input when sold out.

### 3.4 `src/components/Store/CartButton.tsx` (new) and `StoreHeader.tsx`

```tsx
export function CartButton() {
  const { data } = useCart()
  const count = data?.item_count ?? 0
  const badge = count > 99 ? "99+" : String(count)
  return (
    <Button variant="ghost" size="icon" className="relative" asChild>
      <Link to="/cart" aria-label={`Cart, ${count} ${count === 1 ? "item" : "items"}`} data-testid="cart-button">
        <ShoppingCart />
        {count > 0 && (
          <span aria-hidden className="absolute -right-1 -top-1 min-w-5 rounded-full bg-primary px-1 text-center text-[11px] font-semibold leading-5 text-primary-foreground" data-testid="cart-count">
            {badge}
          </span>
        )}
      </Link>
    </Button>
  )
}
```

In `StoreHeader`, render `<CartButton />` between `<Appearance />` and `<StoreUserMenu …/>`, only
when `user` is set.

### 3.5 Update existing tests that assumed the old card

- `tests/responsive-keyboard.spec.ts` ("Category chips, cards and pagination are keyboard
  operable"): focus `card.getByRole("link").first()` instead of the card. Pressing Enter still
  navigates.
- The "Interactive elements expose accessible names" sweep now sees the "+ Add" buttons. They're
  named, so it should pass unchanged. Run it.
- `storefront.spec.ts`, `backoffice-products.spec.ts` and `product-images.spec.ts` only use
  `toContainText` / `toBeVisible` on the card. Run them to confirm.

**Check by hand:**

1. As a visitor, "+ Add" goes to `/login?redirect=/…`. After logging in, you're back on the same
   page.
2. As a customer, "+ Add" shows a toast with "View cart", and the header badge counts up.
3. A sold-out product shows a disabled "Sold out".
4. On the product page, quantity 3 adds 3.
5. Adding more than the stock shows the server's "Only N left in stock" toast.

Commit: `(feat): Add products to the cart from the storefront`

---

## Step 4: Cart, checkout and customer order pages

**Spec:** FR-3, FR-4, FR-5

Routes (file-based, under the `_store` layout). Each one uses
`beforeLoad: ({ location }) => requireUser(location)` and
`head: () => ({ meta: [{ title: pageTitle("…") }] })`.

| File | Path | Title |
|---|---|---|
| `src/routes/_store/cart.tsx` | `/cart` | Cart |
| `src/routes/_store/checkout.tsx` | `/checkout` | Checkout |
| `src/routes/_store/orders.index.tsx` | `/orders` | My orders |
| `src/routes/_store/orders.$orderId.tsx` | `/orders/$orderId` | Order #… |

### 4.1 `/cart`

Components in `src/components/Store/Cart/`:

- **`CartLine.tsx`**, props `{ item: CartItemPublic }`:
  - Layout: a grid with image (64 px), name (a link to the product) + SKU + live unit price,
    `QuantityStepper`, line total, and a remove icon button (`aria-label={`Remove ${item.name}`}`,
    `data-testid="remove-line"`). Below `md`, it stacks into two rows (spec NFR-2).
  - Unavailable lines (`!item.available`): `<Alert variant="destructive">` under the row, with
    "No longer available" when `available_stock === 0`, or
    `` `Only ${item.available_stock} left — lower the quantity` `` otherwise. The line total gets
    `line-through text-muted-foreground`.
  - While this line's mutation is pending: `opacity-60` and `aria-busy`. Compare
    `update.variables?.id` / `remove.variables` with `item.id`.
- **`QuantityStepper.tsx`**, props `{ value, max, label, onChange }`:
  - −, a number `<Input>` (`aria-label={`Quantity for ${name}`}`, `data-testid="quantity-input"`),
    and +. The − and + buttons are named `Decrease quantity of …` / `Increase quantity of …`.
  - It keeps a **local** value and calls `onChange` 400 ms after the last change, through a small
    `useDebouncedCallback` hook (new, `src/hooks/useDebouncedCallback.ts`: `useRef` + `setTimeout`,
    cleared on unmount).
  - It clamps to `[1, max]`, where `max = Math.max(item.quantity, Math.min(item.available_stock, 99))`.
    A line that is already above the stock can still be lowered, but not raised.
  - The local value resyncs when the `value` prop changes (the server's answer).
- **`CartSummary.tsx`**, props `{ cart: CartPublic }`:
  - a `Card` with Items (`item_count`), Total weight, and **Total**, inside an
    `aria-live="polite"` region (spec NFR-1)
  - a **Checkout** button: `<Button asChild><Link to="/checkout">` when `can_place`, else a
    disabled `<Button>` with helper text `"Fix the items marked above to continue"`
    (`data-testid="checkout-button"`)

Page (`cart.tsx`):

- `useCart()`. While pending, show a skeleton.
- Empty (`items.length === 0`): an empty state with a `ShoppingCart` icon, "Your cart is empty"
  and `<Button asChild><Link to="/">Continue shopping</Link></Button>`.
- Otherwise a two-column layout on `lg` (lines on the left, summary on the right, sticky), and
  one column below that.

### 4.2 `/checkout`

```ts
loader: async ({ context }) => {
  const cart = await context.queryClient.fetchQuery({ ...cartQueryOptions, staleTime: 0 })
  if (!cart.can_place) throw redirect({ to: "/cart" })
  return cart
},
```

`beforeLoad` (`requireUser`) runs before the loader, so a visitor never triggers the `/cart`
call (§0.3.3).

Component:

- `const { data: cart } = useSuspenseQuery(cartQueryOptions)`
- A read-only review table: name, qty, unit price, line total. Use `ui/table`. Don't reuse
  `CartLine`.
- Total weight, **Total**, and `<p className="text-sm text-muted-foreground">Payment is simulated, no card is needed.</p>`
- Buttons: **Back to cart** (outline link) and **Place order** (`LoadingButton`,
  `data-testid="place-order"`)
- An error area above the buttons: `<Alert>`, holding the `placeError` state

Place mutation:

```ts
const place = useMutation({
  mutationFn: async () =>
    (await CartService.placeOrder({
      body: { order_id: cart.id!, expected_total: cart.total_price },
    })).data,
  onSuccess: (order) => {
    queryClient.invalidateQueries({ queryKey: cartKeys.all })
    queryClient.invalidateQueries({ queryKey: orderKeys.all })
    queryClient.invalidateQueries({ queryKey: productKeys.all })
    navigate({ to: "/orders/$orderId", params: { orderId: order.id }, search: { placed: true } })
  },
  onError: async (err) => {
    const { status, detail } = apiError(err)
    if (status === 409 && detail.startsWith("Prices changed")) {
      await queryClient.refetchQueries({ queryKey: cartKeys.all })
      setPlaceError({ tone: "warning", text: "Some prices changed. Please review the new total before placing your order." })
    } else if (status === 409) {
      await queryClient.refetchQueries({ queryKey: cartKeys.all })
      showErrorToast(detail)
      navigate({ to: "/cart" })
    } else if (status === 402) {
      setPlaceError({ tone: "error", text: "Your payment was declined." })
    } else {
      setPlaceError({ tone: "error", text: detail, retry: true })   // 503 / network: "Try again" re-runs place.mutate()
    }
  },
})
```

The button is disabled while `place.isPending` (spec G3). After a "prices changed" refetch,
`cart.total_price` is the new value, so the next click sends the right `expected_total`.

### 4.3 `/orders`

- `validateSearch`: `{ page: z.number().int().positive().catch(1).default(1) }`, with
  `stripSearchParams({ page: 1 })`, like `admin/imports.index.tsx`.
- `useQuery(myOrdersQueryOptions(page, MY_ORDERS_PAGE_SIZE))`.
- A list of rows (a `ui/table` on `md+`, stacked cards below). Columns:
  - Order # (a link to `/orders/$orderId`)
  - Placed (date)
  - Items
  - Total
  - State badge
- `PaginationBar` below the list.
- Empty state: "You haven't placed any orders yet." with a link to the store.

### 4.4 `/orders/$orderId`

- `validateSearch`: `{ placed: z.boolean().optional().catch(undefined) }`.
- Loader: validate the uuid (`z.uuid()`), then `ensureQueryData(myOrderQueryOptions(id))`. A 404
  becomes `throw notFound()`, exactly as in `products.$productId.tsx`.
  `notFoundComponent: NotFound`.
- Component: `OrderSummaryHeader` + `OrderItemsTable` + a "Back to my orders" link.
- When `placed` is true, show a success `<Alert>` ("Order placed! We've emailed you a summary.")
  with `tabIndex={-1}` and a ref that is focused on mount. Then remove the param with
  `navigate({ search: {}, replace: true })` so a reload doesn't show it again (spec FR-5.2).
  Run both in one `useEffect` keyed on the order id: focus first, then strip the param. Keep the
  alert visible through local state, so stripping the param doesn't hide it.

### 4.5 `StoreUserMenu.tsx`

Add a "My orders" item (`Package` icon, `<Link to="/orders">`) right after "My account".

**Check by hand** (customer):

1. Add two products and change quantities: the total updates after about 400 ms, and the badge
   follows.
2. Remove a line.
3. In another tab, as the admin, set a product's stock below your quantity. Reload `/cart`: the
   line is flagged and Checkout is disabled. Lower the quantity and Checkout comes back.
4. Go to checkout and place the order: you land on the order page with the alert. The badge is
   0, and "My orders" lists the order.
5. Prices-changed path: open `/checkout`, then raise a price as the admin and click Place order.
   The warning appears with the new total. Click again and the order is placed.

Commit: `(feat): Add cart, checkout and order pages`

---

## Step 5: Backoffice orders

**Spec:** FR-6

### 5.1 Sidebar

In `src/components/Sidebar/AppSidebar.tsx`, add
`{ icon: ShoppingCart, title: "Orders", path: "/admin/orders" }` after "Products".

### 5.2 Components in `src/components/Backoffice/Orders/` (new)

**`OrderActionButton.tsx`** is one generic confirm-and-mutate button, used for both Cancel and
Complete:

```tsx
type Props = {
  order: OrderSummaryPublic
  kind: "cancel" | "complete"
  size?: "sm" | "default"
}
```

- Config per `kind`:
  - label: `"Cancel"` / `"Complete"`
  - button variant: `"outline"` with destructive text / `"default"`
  - dialog title: `Cancel order #${n}?` / `Mark order #${n} as completed?`
  - description: `Its ${order.item_count} items go back into stock and the customer is emailed.`
    / `The customer is emailed.`
  - confirm label: `"Cancel order"` / `"Mark completed"`
  - service call: `OrdersService.cancelOrder` / `completeOrder`
  - success toast: `Order #${n} cancelled` / `Order #${n} completed`
- Accessible name: `` aria-label={`${label} order ${order.number}`} ``.
  `data-testid={`${kind}-order`}`.
- **Disabled** unless `canAct(order)`. The disabled button is wrapped in
  `<Tooltip><TooltipTrigger asChild><span tabIndex={0}>…</span></TooltipTrigger><TooltipContent>Only in-progress orders can be ${kind === "cancel" ? "cancelled" : "completed"}</TooltipContent></Tooltip>`
  (§0.3.11). When enabled, there is no wrapper.
- Dialog + mutation copied from `DeleteProduct.tsx`. Close the dialog on success. `onError`: an
  error toast with the detail (a 409 means someone else acted first, spec FR-6.3). `onSettled`:
  invalidate `orderKeys.all`, and also `productKeys.all` for cancel (stock changed).
- The dialog's **Keep order** / **Close** button is the `DialogClose`. Don't label it "Cancel":
  "Cancel" next to "Cancel order" is confusing.

**`OrderRowActions.tsx`**: a `flex gap-2` with:

- **View**: `<Button variant="ghost" size="sm" asChild><Link to="/admin/orders/$orderId" …>View</Link></Button>`,
  `aria-label={`View order ${order.number}`}`, `data-testid="view-order"`
- `<OrderActionButton kind="cancel" size="sm" />`
- `<OrderActionButton kind="complete" size="sm" />`

The three buttons are always visible, as the spec requires. They are not in a dropdown.

**`columns.tsx`**: `ColumnDef<DataTableFeatures, OrderSummaryPublic>[]`, in the style of
`Imports/columns.tsx`:

| id | Header | Cell |
|---|---|---|
| `number` | Order | `#{number}` as a link to the detail, `font-mono` |
| `user_email` | Customer | muted, truncated |
| `placed_at` | Placed | `formatDate`, or "—" |
| `item_count` | Items | right-aligned |
| `total_weight` | Weight | `formatWeight`, or "—" |
| `total_price` | Total | `formatPrice`, or "—" |
| `state` | State | `OrderStateBadge` |
| `actions` | (`sr-only` "Actions") | `OrderRowActions` |

### 5.3 `src/routes/admin/orders.index.tsx` (new)

```ts
const ordersSearch = z.object({
  tab: z.enum(["in_progress", "completed", "cancelled", "placed", "draft"]).catch("in_progress").default("in_progress"),
  page: z.number().int().positive().catch(1).default(1),
})
// search: { middlewares: [stripSearchParams({ tab: "in_progress", page: 1 })] }
```

- Header: "Orders" / "Review and fulfil customer orders".
- `ui/tabs` (`Tabs` + `TabsList` + `TabsTrigger` for each `ORDER_TABS` entry). Changing the tab
  navigates to `{ tab, page: 1 }`. The tabs only drive the search param: render the table
  **once**, under the tabs, and don't use `TabsContent`.
- `useQuery(adminOrdersQueryOptions({ states: tabStates, page, pageSize: ADMIN_PAGE_SIZE }))`.
  The API takes `state` as a repeated query param: pass `query: { state: states, skip, limit }`.
  Check in the network tab that the generated client serializes the array as
  `state=a&state=b`. If it uses `state[]=` or commas, set the client's array style for this call
  (hey-api `querySerializer: { array: { explode: true, style: "form" } }`).
- Empty state per tab: "No orders here yet".
- Below `md`, the table scrolls horizontally inside its container (spec NFR-2). Wrap it in
  `<div className="overflow-x-auto">` if `DataTable` doesn't already do that.

### 5.4 `src/routes/admin/orders.$orderId.tsx` (new)

- The loader validates the uuid, then `ensureQueryData(adminOrderQueryOptions(id))`. A 404 →
  `notFound()`.
- `OrderSummaryHeader` with
  `actions={<><OrderActionButton kind="cancel" order={order} /><OrderActionButton kind="complete" order={order} /></>}`.
- A "Customer" line with `user_email`, the `OrderTimeline` and the `OrderItemsTable`. A "Back to
  orders" link goes to `/admin/orders`.

**Check by hand** (admin):

1. Place two orders as a customer (Step 4).
2. Both show under **In progress**.
3. Complete one: the dialog, the toast, and the row moves to **Completed**. There, its buttons
   are disabled with a tooltip.
4. Cancel the other: the product's stock on the storefront goes back up.
5. The Drafts tab shows a customer's open cart.
6. Open two admin tabs, cancel in one, then try to complete in the other: an error toast
   appears, and the row updates.

Commit: `(feat): Manage orders in the backoffice`

---

## Step 6: Accessibility and responsive sweep

**Spec:** NFR-1, NFR-2

Extend `tests/responsive-keyboard.spec.ts`:

- **No horizontal page scroll** (mobile viewport): add `/cart` and `/orders` for a logged-in
  customer, using a customer context created in `beforeAll` through the API, and
  `/admin/orders` to the backoffice list.
- **Accessible names**: add `/cart` (with one line), `/checkout`, `/orders`,
  `/orders/<id>`, `/admin/orders` and `/admin/orders/<id>`.
- **Keyboard**:
  1. On `/cart`, Tab to the quantity input, type a new value and wait: the total updates.
  2. Tab to Remove and press Enter: the line disappears.
  3. On `/admin/orders`, Tab to `Cancel order <n>`, press Enter, and the dialog opens with focus
     inside it. Escape closes it, and focus returns to the button.

Run the whole file. Fix any unnamed control or overflow you find.

Commit: `(test): Cover cart and order pages in the accessibility sweeps`

---

## Step 7: Playwright tests

**Spec:** §7 (AC-1 – AC-10)

### 7.1 Helpers: `tests/utils/orders.ts` (new)

```ts
import { createCategory, createProduct, createUser } from "./api"
import { randomEmail, randomPassword } from "./random"   // add them to random.ts if missing

export async function createCustomer() {
  const email = randomEmail()
  const password = randomPassword()
  await createUser({ email, password })
  return { email, password }
}

export async function createStockedProducts(n: number, overrides: Partial<ProductCreate> = {}) {
  const category = await createCategory()
  const products = []
  for (let i = 0; i < n; i++) products.push(await createProduct(category.id, overrides))
  return { category, products }
}

// Customer-side API calls with the customer's own token (api.ts's client is the admin's)
export async function customerApi(email: string, password: string) {
  const base = `${process.env.VITE_API_URL}/api/v1`
  const form = new URLSearchParams({ username: email, password })
  const { access_token } = await (await fetch(`${base}/login/access-token`, { method: "POST", body: form })).json()
  const call = async (method: string, path: string, body?: unknown) => {
    const res = await fetch(`${base}${path}`, {
      method,
      headers: { Authorization: `Bearer ${access_token}`, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`${method} ${path}: ${res.status} ${await res.text()}`)
    return res.json()
  }
  return {
    add: (productId: string, quantity = 1) => call("POST", "/cart/items", { product_id: productId, quantity }),
    place: async () => {
      const cart = await call("GET", "/cart/")
      return call("POST", "/cart/place", { order_id: cart.id, expected_total: cart.total_price })
    },
  }
}

export async function setProduct(id: string, body: ProductUpdate) { /* admin: ProductsService.updateProduct */ }
export async function readProduct(id: string) { /* ProductsService.readProduct */ }

export async function newCustomerPage(browser: Browser) {
  const customer = await createCustomer()
  const context = await browser.newContext({ storageState: { cookies: [], origins: [] } })
  const page = await context.newPage()
  await logInUser(page, customer.email, customer.password)
  return { customer, context, page }
}
```

Check `VITE_API_URL` the way `tests/utils/api.ts` does. If it already includes `/api/v1`, don't
append it twice.

### 7.2 `tests/checkout.spec.ts` (new): storefront flows

Each test creates its own customer and products (§0.3.8–9), and closes its context at the end.

| Test | Covers | Outline |
|---|---|---|
| Visitor "+ Add" asks to log in | AC-1 | Anonymous context, `/?category=<id>`. Click `Add <name> to cart`, expect `/login?redirect=…`. Log in, expect the same category URL |
| Add, change quantity, remove | AC-2, AC-3 | Add A twice (card) and B once (product page, qty 1). Expect `cart-count` 3. `/cart` has 2 lines, quantities 2 and 1, and the total equals the sum (compute the expected string from the known prices). Set B to 3: the total updates. Remove both: empty state |
| Place an order and receive the email | AC-4, AC-7 | Add 2 products. `/cart` → Checkout → Place order. URL `/orders/<id>`, the alert is visible, `order-state` is "In progress", both names are listed, and `cart-count` is hidden. `waitForEmailHtml({ request, query: \`to:${email}\`, timeout: 30_000 })` contains `Order #` and both names. User menu → My orders → the row is listed, and clicking it opens the detail |
| Prices changed before placing | AC-5 | Go to `/checkout`, then `setProduct(id, { price: "99.99" })`. Place order: the warning alert is visible and the total shows `$99.99…`. Place order again: the order page |
| Unavailable line blocks checkout | AC-6 | Add qty 3, then `setProduct(id, { stock: 1 })`. `/cart`: the line alert says "Only 1 left", and `checkout-button` is disabled. Lower to 1: enabled |
| Sold-out product | FR-2.1 | A product with `stock: 0`: the card button is disabled with "Sold out" |
| Customer can't open the backoffice | AC-9 | Customer page → `/admin/orders` → URL `/` |

The email test needs `celery-worker` running. The worker sends within a second or two of
placement. Use a 30 s timeout to absorb a cold worker. If the test environment has no worker,
mark that assertion with `test.skip(!process.env.MAILPIT_HOST, …)`, the same guard the other
Mailpit tests use (check `reset-password.spec.ts`).

### 7.3 `tests/backoffice-orders.spec.ts` (new): admin flows (default admin storage state)

| Test | Covers | Outline |
|---|---|---|
| Complete an order | AC-8 | `customerApi(...).add(p).place()`. `/admin/orders`: the row with `#<number>` is under In progress. `complete-order` → the dialog → "Mark completed" → toast. The Completed tab shows the row, and its `cancel-order` / `complete-order` are disabled |
| Cancel restores stock | AC-8 | Product with stock 5, the customer orders 2 (`readProduct` → 3). Cancel from the **detail page** → toast, the state badge is "Cancelled", and `readProduct` → 5. The storefront product page shows "In stock" |
| Drafts tab | FR-6.2 | `customerApi(...).add(p)` without placing → the Drafts tab lists the customer's email, and its actions are disabled |
| Conflict shows an error | FR-6.3 | Open the row's Cancel dialog. Meanwhile, cancel the same order through the admin API. Confirm in the UI → error toast "Only in-progress orders can be cancelled", and the row's badge updates to Cancelled |

Rows are found with `page.getByRole("row").filter({ hasText: order.number })`. Never by
position: other tests create orders in parallel.

### 7.4 Run everything

```bash
npx bun run test
```

The **whole** suite must pass, not only the new specs: the ProductCard change touches several
existing specs (Step 3.5).

Commit: `(test): Cover cart, checkout and backoffice orders`

---

## Step 8: Docs and final verification

1. `frontend/README.md`: list the new pages (`/cart`, `/checkout`, `/orders`, `/admin/orders`)
   in the routes section, if there is one.
2. Spec header: set **Status** to `Implemented` and link this plan.
3. Final run: `build`, `lint`, `tsc --noEmit -p frontend`, and the full Playwright suite.
4. Manual smoke test in **dark mode** and at a **375 px** width:
   - the cart badge
   - the cart rows stacking
   - the checkout buttons
   - the admin tabs and table scrolling

Commit: `(chore): Document the checkout pages`

---

## Appendix A: Files touched

| File | Change |
|---|---|
| `src/lib/queries/cart.ts`, `src/lib/queries/orders.ts` | New |
| `src/lib/orders.ts` | New: constants, tabs, `canAct`, `apiError` |
| `src/lib/format.ts` | `orderNumber` |
| `src/lib/auth.ts` | `clearSession` drops cart and orders |
| `src/lib/apiErrors.ts` | `isProtected` covers `/cart`, `/checkout`, `/orders` |
| `src/hooks/useCart.ts`, `src/hooks/useAddToCart.ts`, `src/hooks/useDebouncedCallback.ts` | New |
| `src/components/Orders/{OrderStateBadge,OrderItemsTable,OrderSummaryHeader,OrderTimeline}.tsx` | New |
| `src/components/Store/ProductCard.tsx` | Stretched-link restructure and the "+ Add" button |
| `src/components/Store/{AddToCartButton,CartButton}.tsx` | New |
| `src/components/Store/Cart/{CartLine,QuantityStepper,CartSummary}.tsx` | New |
| `src/components/Store/StoreHeader.tsx`, `StoreUserMenu.tsx` | Cart button, "My orders" |
| `src/components/Backoffice/Orders/{OrderActionButton,OrderRowActions,columns}.tsx` | New |
| `src/components/Sidebar/AppSidebar.tsx` | Orders entry |
| `src/routes/_store/products.$productId.tsx` | Quantity + Add to cart |
| `src/routes/_store/{cart,checkout,orders.index,orders.$orderId}.tsx` | New |
| `src/routes/admin/{orders.index,orders.$orderId}.tsx` | New |
| `tests/utils/orders.ts`, `tests/utils/random.ts` | New helpers |
| `tests/checkout.spec.ts`, `tests/backoffice-orders.spec.ts` | New |
| `tests/responsive-keyboard.spec.ts` | Card focus fix, new pages in the sweeps |

## Appendix B: New `data-testid`s and accessible names

| Element | `data-testid` | Accessible name |
|---|---|---|
| Card / product page add button | `add-to-cart` | `Add <product name> to cart` / `<product name> is sold out` |
| Header cart link | `cart-button` | `Cart, N items` |
| Header cart count | `cart-count` | (aria-hidden) |
| Cart quantity input | `quantity-input` | `Quantity for <name>` |
| Stepper buttons | | `Decrease quantity of <name>` / `Increase quantity of <name>` |
| Remove line | `remove-line` | `Remove <name>` |
| Cart checkout button | `checkout-button` | `Checkout` |
| Place order | `place-order` | `Place order` |
| Order state badge | `order-state` | (text) |
| Admin View / Cancel / Complete | `view-order` / `cancel-order` / `complete-order` | `View order <n>` / `Cancel order <n>` / `Complete order <n>` |
