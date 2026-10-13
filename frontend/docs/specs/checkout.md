# Functional Spec: Cart, Checkout and Orders (frontend)

| | |
|---|---|
| **Status** | Implemented |
| **Owner** | Ivan Trivino |
| **Last updated** | 2026-10-12 |
| **Components** | `frontend` (storefront: "+ Add", cart, checkout, my orders; backoffice: Orders; regenerated client; Playwright tests) |
| **Backend spec** | [Cart, Checkout and Orders](../../../backend/docs/specs/checkout.md) (the contract this spec relies on) |
| **Implementation plans** | [Frontend](./checkout-implementation.md) · [Backend](../../../backend/docs/specs/checkout-implementation.md) |
| **Related** | [Storefront and Backoffice](./storefront-backoffice.md) |

## 1. Summary

- Product cards and the product page get an **"+ Add"** button. Visitors are sent to log in first.
- The store header shows a **cart button** with the item count.
- **`/cart`**: edit quantities and remove lines. Lines that became unavailable are flagged.
- **`/checkout`**: a read-only review (lines, total price, total weight) and one **Place order**
  button. There are no address or card fields. Payment is mocked on the server.
- **`/orders/$orderId`**: the order page. Right after placement it shows a confirmation banner.
  **`/orders`** lists the customer's placed orders, opened from a new "My orders" entry in the user
  menu.
- **`/admin/orders`**: the backoffice list, filtered by state, with **View**, **Cancel** and
  **Complete** on every row, plus `/admin/orders/$orderId` with the same actions.

## 2. Goals and non-goals

### Goals

- G1. A logged-in customer goes from "+ Add" to a placed order in at most three clicks after the
  add: cart → checkout → Place order.
- G2. Every server-side rejection (stock, prices changed, payment) is shown in context, and the
  customer can fix it without losing the cart.
- G3. Placing can't be triggered twice: the button is disabled while the request is in flight, and
  the server is idempotent anyway.
- G4. Admins can find in-progress orders and cancel or complete them from the list without opening
  them.
- G5. Keyboard and screen-reader accessible, like the existing pages (axe sweep).

### Non-goals

- Guest carts, address forms, card forms.
- Optimistic cart updates. Every mutation waits for the server's `CartPublic` and uses it as the
  new cache value.
- Real-time updates of the admin list. It refetches when the window regains focus and after each
  action.
- Remembering a pending "+ Add" across the login redirect. After logging in, the visitor comes
  back to the page and clicks again.

## 3. Definitions

The terms from the backend spec §3 apply (Draft, line item, placed order, order number). **Cart
query** means the TanStack Query entry `["cart"]` holding `CartPublic`.

## 4. Backend contract

| Operation | Endpoint | Used by |
|---|---|---|
| Read cart | `GET /cart` | Header badge, `/cart`, `/checkout` |
| Add | `POST /cart/items {product_id, quantity}` | "+ Add" |
| Set quantity / remove | `PATCH /cart/items/{id} {quantity}` / `DELETE /cart/items/{id}` | `/cart` |
| Place | `POST /cart/place {order_id, expected_total}` | `/checkout` |
| My orders | `GET /users/me/orders`, `GET /users/me/orders/{id}` | `/orders`, `/orders/$orderId` |
| Admin orders | `GET /orders/?state&skip&limit`, `GET /orders/{id}`, `POST /orders/{id}/cancel`, `POST /orders/{id}/complete` | `/admin/orders*` |

Errors used by the UI: 409 with the details listed in backend FR-2 and FR-3, 402
`"Payment declined"`, 503 `"Payment service unavailable"`. The client is regenerated
(`openapi-ts`) after the backend lands.

## 5. Functional requirements

### FR-1 Queries and hooks

- **FR-1.1** `lib/queries/cart.ts`: `cartKeys`, `cartQueryOptions` (enabled only when
  `isLoggedIn()`), `staleTime` 30 s. Mutations `addToCart`, `updateCartItem` and `removeCartItem`
  write the returned `CartPublic` into the cache with `setQueryData`. They don't invalidate it.
- **FR-1.2** `hooks/useAddToCart.ts`: wraps the add mutation.
  - **Visitor**: navigate to `/login?redirect=<current href>`.
  - **Success**: toast `"Added to cart"`, with an action **View cart**.
  - **409 / 404**: an error toast with the server's `detail` (`"Only 3 left in stock"`).
- **FR-1.3** `lib/queries/orders.ts`: `myOrdersQueryOptions(page)`, `myOrderQueryOptions(id)`,
  `adminOrdersQueryOptions({states, page})`, `adminOrderQueryOptions(id)`. Cancel and Complete
  mutations invalidate `["orders"]` and `["products"]` (stock changed on cancel).
- **FR-1.4** Logging out removes `["cart"]` and `["orders"]` from the cache (`clearSession`).
- **FR-1.5** `lib/format.ts` gains `formatWeight(kg)` (`"1.25 kg"`) and `orderNumber(id)` (first 8
  hex chars uppercased, matching the backend).

### FR-2 "+ Add" on the storefront

- **FR-2.1** **ProductCard.** Today the whole card is a `<Link>`, and a button can't be nested
  inside an anchor. The card becomes an `<article>`:
  - The image and the name keep a link to the product page. The name's link stretches over the
    card with an `::after` overlay, so the whole card stays clickable.
  - A separate **"+ Add"** button sits next to the price, above the overlay (`relative z-10`).
  - Accessible name: `"Add <product name> to cart"`.
  - Disabled with the text `"Sold out"` when `stock === 0`.
  - Shows a spinner while its mutation is pending.
- **FR-2.2** **Product page** (`/products/$productId`): a quantity input (1 to `min(stock, 99)`)
  and an **"Add to cart"** button below the stock badge, with the same states as FR-2.1.
- **FR-2.3** **Header**: a cart icon button for logged-in users, between the search bar and the
  user menu. It shows `item_count` as a badge (hidden at 0, `99+` above 99). Accessible name:
  `"Cart, N items"`. It links to `/cart`. Hidden for visitors.

### FR-3 `/cart` (`_store/cart.tsx`, `beforeLoad: requireUser`)

- **FR-3.1** Empty cart: an empty state with `"Your cart is empty"` and a **Continue shopping**
  link to `/`.
- **FR-3.2** One row per line:
  - image, name (links to the product), SKU, live unit price
  - a quantity stepper (−, input, +), between 1 and `min(available_stock, 99)`
  - the line total
  - a **Remove** button (accessible name `"Remove <name>"`)

  Changes to the quantity are debounced by 400 ms before the PATCH is sent. A row whose request
  is pending is dimmed.
- **FR-3.3** **Unavailable line** (`available: false`): the row gets a destructive alert:
  - `"No longer available"` if `available_stock === 0`
  - `"Only N left — lower the quantity"` otherwise

  The line total is struck through, and the line doesn't count in the summary.
- **FR-3.4** Summary card: items, total weight, total price. A **Checkout** button links to
  `/checkout`. It is disabled when `can_place` is false, with the reason as helper text.

### FR-4 `/checkout` (`_store/checkout.tsx`, `beforeLoad: requireUser`)

- **FR-4.1** The loader fetches the cart fresh (`fetchQuery`, ignoring `staleTime`). If
  `can_place` is false, it redirects to `/cart`.
- **FR-4.2** Read-only review:
  - a table of lines: name, quantity, unit price, line total
  - total weight and total price
  - a note: `"Payment is simulated, no card is needed."`
  - **Back to cart**
  - **Place order** (a `LoadingButton`, disabled while pending)
- **FR-4.3** Place order sends `{order_id: cart.id, expected_total: cart.total_price}`. Outcomes:

  | Response | UI |
  |---|---|
  | 200 | Invalidate `["cart"]`, `["orders"]` and `["products"]`. Navigate to `/orders/$orderId?placed=true` |
  | 409 `"Prices changed…"` | Refetch the cart and stay on the page. Warning alert: `"Some prices changed. Please review the new total before placing your order."` |
  | 409 unavailable / empty | Refetch the cart, navigate to `/cart`, error toast with `detail` |
  | 402 | Error alert `"Your payment was declined."`. The cart is unchanged |
  | 503 / network | Error alert with a **Try again** button (safe, the server is idempotent) |

### FR-5 Customer orders

- **FR-5.1** `/orders` (`_store/orders.index.tsx`, `requireUser`) is a paginated list (10 per page,
  `PaginationBar`). Columns: order number, placed date, items, total, state badge. Each row links to
  the detail page. Empty state: `"You haven't placed any orders yet."`
- **FR-5.2** `/orders/$orderId` (`_store/orders.$orderId.tsx`, `requireUser`) shows:
  - the header: `Order #3F9A12C0`, the state badge and the placed date
  - the lines table, with the fixed values
  - the totals and the payment reference
  - **With `?placed=true`**: a success alert `"Order placed! We've emailed you a summary."` with
    focus moved to it. The param is removed with `replace` so a reload doesn't show it again.
  - A 404 shows the existing NotFound component.
- **FR-5.3** `StoreUserMenu` gets a **"My orders"** entry (icon `Package`) under "My account".
- **FR-5.4** `OrderStateBadge`, shared with the backoffice:

  | State | Label | Badge variant |
  |---|---|---|
  | `draft` | Draft | `outline` |
  | `in_progress` | In progress | `default` |
  | `completed` | Completed | `secondary` with a check icon |
  | `cancelled` | Cancelled | `destructive` |

### FR-6 Backoffice orders

- **FR-6.1** Sidebar: an **Orders** entry (icon `ShoppingCart`) after "Products".
- **FR-6.2** `/admin/orders` (`admin/orders.index.tsx`), using `DataTable`:
  - **State filter**: tabs **In progress** (default) · **Completed** · **Cancelled** ·
    **All placed** · **Drafts**. The tab is kept in the search params (`?state=`).
  - **Columns**: Order # (links to the detail) · Customer email · Placed (date, or "—" for
    Drafts) · Items · Weight · Total · State · Actions.
  - **Actions**: three visible buttons on every row, as requested. They aren't hidden in a menu.
    - **View** opens the detail page.
    - **Cancel** opens a confirm dialog: `"Cancel order #X? Its N items go back into stock and the
      customer is emailed."`
    - **Complete** opens a confirm dialog: `"Mark order #X as completed? The customer is emailed."`

    Cancel and Complete are **disabled** unless `state === "in_progress"`, with a tooltip
    explaining why. Accessible names include the order number (`"Cancel order 3F9A12C0"`).
  - **Pagination**: 20 per page.
- **FR-6.3** After Cancel or Complete: a success toast, and the list and detail queries are
  invalidated. On 409 (someone else acted first): an error toast with `detail` and a refetch, so
  the row shows its real state.
- **FR-6.4** `/admin/orders/$orderId` shows the same content as FR-5.2, plus the customer email
  and the timeline timestamps (created, placed, completed or cancelled). The Cancel and Complete
  buttons in the header follow the same rules as FR-6.2.

## 6. Non-functional requirements

- **NFR-1 Accessibility.** Quantity steppers are a labelled `<input type="number">` (`"Quantity
  for <name>"`). The − and + buttons are named. Cart totals sit in an `aria-live="polite"`
  region, so quantity changes are announced. Confirm dialogs trap focus and return it to the
  button that opened them. The new pages are added to the axe sweeps
  (`responsive-keyboard.spec.ts`).
- **NFR-2 Responsive.** Below `md`, the cart rows stack (image and name on top, stepper and total
  below), and the admin table scrolls horizontally inside its card, as the existing tables do.
- **NFR-3 Money.** Amounts are formatted with `formatPrice()` from the API's decimal strings. The
  UI never sums prices itself. Every total shown comes from the server.

## 7. Acceptance criteria (Playwright)

- **AC-1** A visitor clicks "+ Add" on a card, lands on `/login?redirect=…`, logs in and is back on
  the same page.
- **AC-2** A customer adds two products (one of them twice). The header badge shows 3, and `/cart`
  shows 2 lines with quantities 2 and 1 and the right total.
- **AC-3** Changing a quantity updates the total. Removing the last line shows the empty state.
- **AC-4** Checkout → Place order → the order page shows the success alert, the state
  `In progress` and the lines. The header badge goes back to 0. Mailpit received
  `Order #<number> confirmed`.
- **AC-5** An admin raises a product's price while the customer is on `/checkout` → Place order
  shows the "prices changed" alert with the new total, and a second click places the order.
- **AC-6** Stock falls below the cart quantity (admin edit) → `/cart` flags the line, and Checkout
  is disabled until the quantity is lowered.
- **AC-7** "My orders" lists the placed order, and clicking it opens the detail page.
- **AC-8** An admin opens Orders: the order is under **In progress**. Complete → confirm → it moves
  to **Completed**, and its Cancel and Complete buttons are disabled. A second order → Cancel →
  the product's stock on the storefront goes back up.
- **AC-9** A customer navigating to `/admin/orders` is redirected to `/`.
- **AC-10** The new pages pass the axe sweep in light and dark mode, and are keyboard-operable
  (add, change quantity, place, and admin cancel through the dialog).

## 8. Open questions / future work

- A **mini-cart sheet** (`ui/sheet`) instead of navigating to `/cart` after "+ Add".
- Replaying the pending "+ Add" after login (`?add=<productId>` in the redirect).
- Admin search by customer email or order number (needs a backend filter).
- Showing order emails sent and their status (`order_notification`) on the admin detail page.
