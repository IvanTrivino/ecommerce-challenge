# Functional Spec: Cart, Checkout and Orders

| | |
|---|---|
| **Status** | Implemented (backend) |
| **Owner** | Ivan Trivino |
| **Last updated** | 2026-10-12 |
| **Components** | `backend` (new `order` / `cart_item` / `order_notification` tables, `cart` and `orders` APIs, checkout service, mocked payments gateway, Celery email task and beat job, email templates, migration `0006`), `frontend` (storefront cart, checkout and order pages, backoffice Orders page) |
| **Frontend spec** | [Checkout (frontend)](../../../frontend/docs/specs/checkout.md) |
| **Implementation plans** | [Backend](./checkout-implementation.md) · [Frontend](../../../frontend/docs/specs/checkout-implementation.md) |
| **Related** | [Product imports](./product-imports.md) (D17: writes on `product`), [Product search indexer](./product-search-indexer.md) (outbox) |

## 1. Summary

Logged-in customers build a cart and place an order. Admins follow orders from the backoffice.

- An **order** is the cart and the purchase in one entity. The first **"+ Add"** creates the
  customer's order in state **Draft**. Each user has at most one Draft at a time. Later adds put
  more **line items** (`cart_item`) into it or raise their quantities.
- **Placing** the order runs the checkout pipeline in **one database transaction**:
  - validate the cart and the inventory
  - lock the products and decrement their stock
  - fix the prices and weights onto the line items, and compute the order totals
  - call the **mocked payments gateway** (always succeeds)
  - move the order to **In Progress**
- The customer receives an **order summary email**. A **Celery task** sends it, and it is recorded
  in the same transaction as the state change, so a lost enqueue is recovered (D9).
- Admins see every placed order in the backoffice, with **View**, **Cancel** and **Complete**.
  Cancel puts the stock back. Both send the customer an email.
- Customers see their own placed orders, read-only.

```
            "+ Add"             place (checkout)            admin: Complete
  (none) ───────────▶ draft ───────────────────▶ in_progress ──────────────▶ completed
                                                     │
                                                     │ admin: Cancel (restock)
                                                     ▼
                                                 cancelled
```

## 2. Goals and non-goals

### Goals

- G1. A logged-in user can add products to a cart, change quantities, remove lines, review the
  cart and place the order with one click.
- G2. **No overselling.** Two customers placing orders at the same time can never take stock below
  zero. A placed order is never short of stock.
- G3. **Idempotent placement.** A double click, a retried request or two open tabs place an order
  at most once, and charge it at most once.
- G4. A placed order is a fixed record. Later changes to a product's price, weight, name or
  existence never alter the order's lines or totals.
- G5. The customer receives exactly one summary email per placed order in normal operation, and
  at least one if the worker or broker fails (at-least-once, D9). The same applies to the cancel
  and complete emails.
- G6. Admins can list orders, filter them by state, inspect one, cancel it (with restock) or
  complete it.
- G7. Stock changes from placement and cancellation show on the storefront straight away
  (product cache invalidation).

### Non-goals

- Guest carts. Visitors must log in before "+ Add" (frontend redirects to login).
- Shipping address, shipping cost, taxes, discounts and coupons.
- A real payment provider, card forms, refunds. The gateway is a mock (D7). Cancelling an order
  doesn't issue a refund.
- Stock reservation while an order is a Draft. Stock is checked when adding, but only placement
  takes it.
- Expiring or cleaning up abandoned Drafts.
- Customers cancelling their own orders.
- Editing a placed order (adding or removing lines, changing quantities).
- Partial fulfilment, shipments, tracking.

## 3. Definitions

| Term | Meaning |
|---|---|
| **Order** | An `order` row. Its `state` is one of `draft`, `in_progress`, `completed`, `cancelled`. |
| **Draft / cart** | The user's single order in state `draft`. "Cart" is the customer-facing name. |
| **Line item** | A `cart_item` row: one product and its quantity in one order. |
| **Placed order** | An order in `in_progress`, `completed` or `cancelled`. It has `placed_at` and fixed totals. |
| **Fixed values** | `unit_price` and `unit_weight` copied from the product onto each line when the order is placed. Null while the order is a Draft. |
| **Live values** | The product's current `price` and `weight`. A Draft's totals are computed from them. |
| **Order number** | The first 8 hex chars of the order id, uppercased (e.g. `3F9A12C0`). Display only. Lookups always use the full id. |
| **Notification** | An `order_notification` row: one email to send for one order event (`placed`, `cancelled`, `completed`). |

## 4. Decisions

| # | Decision | Reason |
|---|---|---|
| D1 | **The cart is the Draft order** (no separate cart table). This follows the ERD. | One entity, one set of line items. Placement is a state change, not a copy. |
| D2 | **At most one Draft per user**, enforced by a partial unique index `ux_order_user_draft ON "order" (user_uuid) WHERE state = 'draft' AND NOT is_deleted`. | Two tabs clicking "+ Add" at the same time can't create two carts. The `IntegrityError` is handled by re-reading the winner's Draft. |
| D3 | **One line per product per order**: `UNIQUE (order_uuid, product_uuid)`. Adding a product that is already in the cart raises its `quantity`. Every cart write holds the Draft row lock (FR-2.6), so a plain ORM read-then-write is safe: concurrent adds of the same product run one after the other and never lose an increment. | Matches how carts behave. The unique constraint is a safety net, not a control flow. |
| D4 | **Prices and weights are fixed at placement**, not at add. Drafts show live values. | The customer pays the price shown at checkout, not a stale price from days ago. The placed order is a fixed record (G4). |
| D5 | **Price-change guard.** `place` takes the `expected_total` the customer saw. If the total computed under lock differs → 409 `"Prices changed, please review your cart"` and nothing is written. | A price edit between the review page and the click can't silently charge a different amount. |
| D6 | **Stock is decremented at placement, under row locks, through the ORM.** The service loads the order's products `SELECT … FOR UPDATE` **ordered by id**, checks `stock >= quantity` for every line, then decrements. Cancel locks the same way and increments. | Row locks serialize concurrent checkouts on the same product (G2). Locking in id order prevents deadlocks between two carts that share products. Going through the ORM keeps product-imports D17 ("nothing else issues a Core write on `product`"). `stock` isn't a search field, so no outbox event is emitted. |
| D7 | **Mocked payments gateway behind an interface.** `PaymentsGateway.charge(order_id, amount, currency) -> PaymentResult` (a protocol). The `MockPaymentsGateway` returns `approved` with reference `mock_<order number>`, without I/O. It is injected as a FastAPI dependency so tests can replace it with a declining double. | The diagram's Payments Gateway box (adapters, retries) stays a real seam. A real provider is a new adapter, not a rewrite. The order id is the idempotency key a real provider would get. |
| D8 | **The payment call happens inside the placement transaction, after the stock checks and before the commit.** A decline or an error rolls everything back (stock, fixed values, state) and answers 402 or 503. | With a mock that never waits, this is the simplest correct ordering. It costs no locks held during real network I/O. With a real provider this changes to a two-step flow (§8). |
| D9 | **Emails go through an `order_notification` table (a dedicated outbox).** The row is inserted **in the same transaction** as the state change. After the commit, the API enqueues `send_order_notification(id)`. A beat job re-enqueues rows still `pending` after 2 minutes. The task claims the row `FOR UPDATE SKIP LOCKED`, sends, and marks it `sent`. `UNIQUE (order_uuid, kind)`. | A crash between commit and enqueue, or a lost broker message, can't lose an email. `SKIP LOCKED` together with the status check makes duplicate deliveries and the re-enqueue a no-op while a send is running. The existing `outbox_event` table can't be reused: the search indexer claims **every** pending row whatever its topic. |
| D10 | **Delivery is at-least-once.** If the worker dies after SMTP accepted the message but before the commit, the email is sent again. | Exactly-once delivery over SMTP isn't possible. A rare duplicate summary is better than a missing one. |
| D11 | **Allowed transitions:** `draft → in_progress` (customer, place), `in_progress → completed` and `in_progress → cancelled` (admin). Completed and cancelled are final. Any other transition → 409. The service takes the order row `FOR UPDATE` before checking. | Simple, auditable lifecycle. The row lock makes Cancel and Complete racing each other, or a double Cancel, resolve to exactly one winner, with a single restock. |
| D12 | **Placement is idempotent by order id.** `POST /cart/place` carries the Draft's `order_id`. If that order is already placed and belongs to the caller → 200 with the order, nothing done. | A double click or retried request returns the same result instead of a confusing "cart is empty" (G3). |
| D13 | **Totals are stored at placement** (`total_price`, `total_weight`), and are null while the order is a Draft. Products without a weight count as 0 kg. | Admin lists and emails read stored numbers without joining products. `weight` is nullable on `product`. |
| D14 | **Adding checks stock softly.** `quantity` (after merging with the existing line) must be ≤ the product's current stock, or 409. Placement re-checks under lock. | Early feedback for the customer. Only placement guarantees correctness. |
| D15 | **Products in a cart can disappear.** If a product is soft-deleted, or its stock falls below the line's quantity, the cart shows the line as unavailable (`available: false`, `available_stock`), and placement → 409 `"Some items in your cart are unavailable"`. The line is not removed automatically. | The customer sees what happened and decides (lower the quantity or remove the line). The API never silently changes a cart. |
| D16 | **Cache:** placement and cancellation call `invalidate_quietly(PRODUCTS)` **after the commit**. Orders and carts aren't cached. | Product reads (stock badges) are cached for 5 minutes. Carts are per user and change often, so caching them gains nothing. |
| D17 | **Table names follow the ERD:** `"order"` and `cart_item`, with `*_uuid` foreign keys like `product.category_uuid`. | Consistent with the existing schema. `order` is a reserved word, but SQLAlchemy and Alembic quote it automatically, as they already do for `"user"`. Raw SQL must quote it. |

## 5. Functional requirements

### FR-1 Data model (migration `0006`)

- **FR-1.1** `order` (extends `Base`: `id`, `is_deleted`, `created_at`, `updated_at`)

  | Column | Type | Notes |
  |---|---|---|
  | `user_uuid` | uuid FK → `user.id`, indexed | Owner |
  | `state` | varchar(20) | `CHECK (state IN ('draft','in_progress','completed','cancelled'))`. Default `draft` |
  | `total_price` | numeric(12,2) null | Set at placement (D13) |
  | `total_weight` | numeric(12,3) null | Set at placement. Products without weight count as 0 |
  | `currency` | char(3) | `USD`. Single-currency store, stored for the gateway and the email |
  | `payment_reference` | varchar(100) null | Returned by the gateway |
  | `placed_at`, `completed_at`, `cancelled_at` | timestamptz null | Set by the matching transition |

  Indexes: `ux_order_user_draft` (D2). `ix_order_state_placed_at (state, placed_at DESC)` for the
  admin list. `ix_order_user_placed_at (user_uuid, placed_at DESC) WHERE state <> 'draft'` for
  "My orders".
  Check: `state = 'draft' OR (placed_at IS NOT NULL AND total_price IS NOT NULL AND total_weight IS NOT NULL)`.

- **FR-1.2** `cart_item` (extends `Base`)

  | Column | Type | Notes |
  |---|---|---|
  | `order_uuid` | uuid FK → `order.id` `ON DELETE CASCADE`, indexed | |
  | `product_uuid` | uuid FK → `product.id` | No cascade: products are only soft-deleted |
  | `quantity` | int | `CHECK (quantity BETWEEN 1 AND 99)` (`MAX_QUANTITY_PER_ITEM`) |
  | `unit_price` | numeric(10,2) null | Fixed at placement (D4) |
  | `unit_weight` | numeric(10,3) null | Fixed at placement. Stays null when the product has no weight |
  | `product_name`, `product_sku` | varchar(255) / varchar(100) null | Fixed at placement, so the order and the email still read correctly if the product is renamed or deleted |

  Constraint: `UNIQUE (order_uuid, product_uuid)` (D3). Lines are hard-deleted when removed from a
  Draft. They are never deleted after placement.

- **FR-1.3** `order_notification` (extends `ModelBase`, like `outbox_event`)

  | Column | Type | Notes |
  |---|---|---|
  | `id` | bigint identity PK | |
  | `order_uuid` | uuid FK → `order.id` | |
  | `kind` | varchar(20) | `placed` \| `cancelled` \| `completed` |
  | `status` | varchar(10) | `pending` \| `sent` \| `failed` \| `skipped`. Default `pending` |
  | `attempts` | int, default 0 | |
  | `available_at` | timestamptz | When beat may (re-)enqueue the row. Insert: `now + ORDER_NOTIFICATION_REQUEUE_AFTER_SECONDS`. After a failed attempt: `now + backoff` |
  | `last_error` | text null | |
  | `created_at`, `sent_at` | timestamptz | |

  Constraints: `UNIQUE (order_uuid, kind)`. Partial index `ix_order_notification_pending (available_at) WHERE status = 'pending'`.

### FR-2 Cart API (customer)

All endpoints require a logged-in user (`CurrentUser`). Superusers can use them too.

- **FR-2.1** `CartPublic`:

  | Field | Type | Notes |
  |---|---|---|
  | `id` | uuid \| null | The Draft's id. Null when the user has no Draft yet |
  | `items` | `CartItemPublic[]` | Oldest line first |
  | `item_count` | int | Sum of quantities (header badge) |
  | `total_price` | decimal | Σ live price × quantity over **available** lines |
  | `total_weight` | decimal | Σ live weight × quantity over available lines, missing weight = 0 |
  | `can_place` | bool | `items` not empty and every line `available` |

  `CartItemPublic`: `id`, `product_id`, `name`, `sku`, `image_url`, `unit_price` (live), `quantity`,
  `line_total`, `available` (product live and `stock >= quantity`), `available_stock` (int, 0 if
  the product is deleted).

- **FR-2.2** `GET /api/v1/cart` → 200 `CartPublic`. Never creates a Draft. With no Draft, it
  returns an empty cart with `id: null`.
- **FR-2.3** `POST /api/v1/cart/items` body `{product_id, quantity = 1}` (`quantity` 1–99, else
  422). This is the **"+ Add"** action.
  1. Product not found or soft-deleted → 404 `"Product not found"`.
  2. Get the user's Draft, or create it (D2: on a unique violation, roll back and re-read).
  3. Upsert the line (D3). If the merged quantity would exceed 99 → 409
     `"You can add at most 99 of this product"`. If it exceeds the product's stock → 409
     `"Only N left in stock"` (D14). Nothing is written in either case.
  4. At most `CART_MAX_ITEMS` (50) distinct lines. Adding the 51st product → 409 `"Your cart is full"`.

  → 200 `CartPublic`.
- **FR-2.4** `PATCH /api/v1/cart/items/{item_id}` body `{quantity}` (1–99) **sets** the quantity
  (it doesn't add to it). The line must belong to the caller's Draft, else 404 `"Cart item not found"`.
  The stock check works as in FR-2.3, except when the new quantity is lower than the current one.
  Lowering is always allowed, because it is how a customer fixes an unavailable line. → 200 `CartPublic`.
- **FR-2.5** `DELETE /api/v1/cart/items/{item_id}` → 200 `CartPublic`. Same ownership rule. An
  emptied Draft stays and is reused by the next add.
- **FR-2.6** Every cart write (FR-2.3 to FR-2.5) locks the Draft row first
  (`SELECT … WHERE user_uuid = :me AND state = 'draft' FOR UPDATE`). Placement holds the same
  lock, so a cart write that runs during a placement waits for it. Postgres then re-checks the
  `WHERE` on the updated row, and the order is no longer a Draft. The add therefore creates a
  **new** Draft, and a PATCH or DELETE answers 404 `"Cart item not found"`. A line can never be
  added to an order that was just placed.

### FR-3 Place order (checkout)

- **FR-3.1** `POST /api/v1/cart/place` body `{order_id: uuid, expected_total: decimal}`. This
  follows the diagram's layers:
  - **Checkout Handler** (router): input validation through the Pydantic schema, plus auth.
  - **Checkout Service**: validators, then the place-order business logic.
  - **Order Service**: the state change and the payment through the **Payments Gateway**.
- **FR-3.2** Steps, all in **one transaction**. The first failure rolls back and answers with the
  status and detail shown:

  | # | Step | Failure |
  |---|---|---|
  | 1 | Load `order_id` `FOR UPDATE`. Not found, or not owned by the caller | 404 `"Order not found"` |
  | 2 | Already `in_progress`, `completed` or `cancelled` | **200** with `OrderPublic`, nothing done (D12) |
  | 3 | **Cart validator**: at least one line | 409 `"Your cart is empty"` |
  | 4 | Lock the products `FOR UPDATE ORDER BY id` (D6) | |
  | 5 | **Inventory validator**: every product live and `stock >= quantity` | 409 `"Some items in your cart are unavailable"` |
  | 6 | Compute the total from the locked live prices. Compare it with `expected_total` | 409 `"Prices changed, please review your cart"` (D5) |
  | 7 | Decrement stock. Fix `unit_price`, `unit_weight`, `product_name`, `product_sku` on each line. Set `total_price`, `total_weight` | |
  | 8 | `gateway.charge(order.id, total_price, currency)` | Declined → 402 `"Payment declined"`. Gateway error → 503 `"Payment service unavailable"` |
  | 9 | `state = in_progress`, `placed_at = now`, `payment_reference`. Insert `order_notification(kind='placed')` | |
  | 10 | Commit | |

  After the commit: `invalidate_quietly(PRODUCTS)` (D16), then enqueue `send_order_notification`.
  An enqueue failure is logged and doesn't fail the request (D9: beat recovers it).
  → 200 `OrderPublic`.
- **FR-3.3** The validators are small classes with one method,
  `validate(order, products) -> None` (raise `ConflictError`), run in order by the checkout
  service. New checks (address, limits per customer, …) are added as new validators, matching the
  diagram's "…" box.
- **FR-3.4** Steps 3 to 6 change nothing, so a 409 leaves the Draft exactly as it was. The
  frontend then refetches the cart, which explains the problem line by line (FR-2.1 `available`).

### FR-4 Orders API

- **FR-4.1** `OrderPublic`: `id`, `number`, `state`, `user_id`, `user_email`, `total_price`,
  `total_weight`, `currency`, `item_count`, `payment_reference`, `placed_at`, `completed_at`,
  `cancelled_at`, `created_at`, `items: OrderItemPublic[]`.
  `OrderItemPublic`: `id`, `product_id`, `name`, `sku`, `quantity`, `unit_price`, `unit_weight`,
  `line_total`. These are all fixed values (D4). For a Draft (admin view only), `name` and `sku`
  come from the live product and the money fields are null.
  `OrderSummaryPublic` (lists): the same without `items`.
  `OrdersPublic {data, count}`.
- **FR-4.2** **Customer**, logged in:
  - `GET /api/v1/users/me/orders?skip&limit` lists the caller's **placed** orders, newest
    `placed_at` first.
  - `GET /api/v1/users/me/orders/{order_id}` returns one order. 404 `"Order not found"` if it is
    someone else's order or a Draft.
- **FR-4.3** **Admin**, superusers only, under `/api/v1/orders`:

  | Endpoint | Behaviour |
  |---|---|
  | `GET /orders/?state&skip&limit` | `state` optional, one of the four, repeatable (`?state=in_progress&state=cancelled`). Default: every **placed** state (Drafts hidden). Placed orders sort by `placed_at` desc, Drafts by `updated_at` desc. `limit` ≤ 100 |
  | `GET /orders/{order_id}` | `OrderPublic`. 404 `"Order not found"` |
  | `POST /orders/{order_id}/cancel` | FR-5.1 |
  | `POST /orders/{order_id}/complete` | FR-5.2 |

### FR-5 Admin transitions

- **FR-5.1** **Cancel**, in one transaction:
  1. Lock the order `FOR UPDATE`. If it isn't `in_progress` → 409 `"Only in-progress orders can be cancelled"`.
  2. Lock the products `FOR UPDATE ORDER BY id` and add each line's quantity back to `stock`
     (soft-deleted products too, so stock stays correct if the product is restored).
  3. `state = cancelled`, `cancelled_at = now`. Insert `order_notification(kind='cancelled')`.
  4. Commit. Invalidate `PRODUCTS`. Enqueue the notification.

  → 200 `OrderPublic`. No refund call (non-goal), and the payment reference stays.
- **FR-5.2** **Complete**: lock the order. If it isn't `in_progress` → 409
  `"Only in-progress orders can be completed"`. Set `state = completed` and `completed_at`, insert
  `order_notification(kind='completed')`, commit, enqueue. Stock doesn't change. → 200 `OrderPublic`.

### FR-6 Notifications (Celery)

- **FR-6.1** Task `app.tasks.send_order_notification(notification_id: int)`. It does **not** use
  Celery retries. Beat is the only retry mechanism (FR-6.2), so the two can never overlap.
  1. In a transaction, `SELECT … WHERE id = :id AND status = 'pending' FOR UPDATE SKIP LOCKED`.
     If no row comes back, return (already sent, or another worker is sending it).
  2. If `settings.emails_enabled` is false → `status = skipped` and return. Logged once at `INFO`.
  3. Load the order with its lines and user. Render the template for `kind` (FR-6.3). Send it,
     and treat any non-250 SMTP result as a failure.
  4. On success: `status = sent`, `sent_at = now`, `attempts += 1`. Commit.
  5. On an SMTP or network error: `attempts += 1`, `last_error`, `available_at = now + 30 s × 2^(attempts-1)`.
     When `attempts` reaches `ORDER_NOTIFICATION_MAX_ATTEMPTS` (5), set `status = failed`. Commit.

  The row lock is held during the SMTP call. That keeps concurrent copies from sending the same
  email twice.
- **FR-6.2** Beat `requeue-order-notifications`, every minute: enqueue every `pending` row with
  `available_at <= now`, oldest first, at most 500 per run. It handles both a lost first enqueue
  (D9: `available_at` starts 2 minutes after insert) and retries after failures (FR-6.1 step 5).
  A row still being sent is skipped by its lock (FR-6.1 step 1).
- **FR-6.3** Templates in `app/email-templates/`, rendered with `render_email_template()` like the
  existing ones:

  | Kind | Template | Subject |
  |---|---|---|
  | `placed` | `order_placed.html` | `{PROJECT_NAME} - Order #{number} confirmed` |
  | `cancelled` | `order_cancelled.html` | `{PROJECT_NAME} - Order #{number} cancelled` |
  | `completed` | `order_completed.html` | `{PROJECT_NAME} - Order #{number} completed` |

  The **placed** email contains:
  - the order number and the placement date (UTC)
  - a table of lines: name, SKU, quantity, unit price, line total
  - the total price and total weight
  - the payment reference
  - a link to `{FRONTEND_HOST}/orders/{id}`

  The other two contain the number, the new state, the total and the same link. Every value comes
  from the fixed order data. Jinja autoescaping is **on** for these templates, because product
  names come from admins and CSV imports.
- **FR-6.4** Generator functions `generate_order_email(order, kind) -> EmailData` sit next to
  `generate_reset_password_email()` in `email_service.py`.

### FR-7 Configuration

| Setting | Default | Notes |
|---|---|---|
| `CART_MAX_ITEMS` | 50 | Distinct lines per cart |

The per-line maximum (99) is **not** a setting. It is a code constant, `MAX_QUANTITY_PER_ITEM`,
shared by the DB check constraint and the request schemas, so the two can never disagree.
| `ORDER_CURRENCY` | `USD` | |
| `ORDER_NOTIFICATION_REQUEUE_AFTER_SECONDS` | 120 | FR-1.3, FR-6.2 |
| `ORDER_NOTIFICATION_MAX_ATTEMPTS` | 5 | FR-6.1 |

### FR-8 Code layout

Follows the existing layers:

```
models/orders/{order.py, cart_item.py, order_notification.py}
repositories/orders/{order_repository.py, cart_item_repository.py, order_notification_repository.py}
schemas/orders/{cart.py, order.py}
services/orders/
  cart_service.py           # FR-2
  checkout/
    service.py              # FR-3 orchestration (Checkout Service)
    validators.py           # CartNotEmpty, InventoryAvailable, PriceUnchanged
  order_service.py          # place / cancel / complete transitions (Order Service)
  payments.py               # PaymentsGateway protocol, MockPaymentsGateway (Payments Gateway)
  notifications.py          # enqueue + task body (FR-6)
api/routes/cart/router.py
api/routes/orders/router.py # admin
api/routes/users/router.py  # + /me/orders
api/deps/orders.py          # CartServiceDep, CheckoutServiceDep, OrderServiceDep, PaymentsGatewayDep
```

## 6. Non-functional requirements

- **NFR-1 Security.** Every cart and "my orders" query filters by `user_uuid = current_user.id`.
  The order and item ids in paths are never trusted alone, so another user's id answers 404,
  never 403 (no enumeration). Admin endpoints use `get_current_active_superuser`. Email templates
  autoescape. Money is `Decimal` end to end and never `float`.
- **NFR-2 Consistency.** Every write path holds the order row lock, and placement and cancel also
  hold the product locks in id order. No path takes them in another order, so these flows can't
  deadlock each other. Product-import batches write `product` with Core upserts and don't take
  locks in id order, so a deadlock with a checkout is possible but unlikely. It surfaces as an
  `OperationalError` (500), and the customer can retry. Accepted, see product-imports §8.
- **NFR-3 Performance.** Placement costs a constant number of statements plus one `UPDATE` per line
  (≤ 50). Target: p95 under 150 ms for a 10-line cart on the dev stack.
- **NFR-4 Observability.** Placement, cancel and complete log one `INFO` line each with the order
  id, user id, total and line count. The notification task logs each send or failure with the
  notification id.

## 7. Acceptance criteria

- **AC-1** Without a token, every cart and order endpoint → 401. A customer calling an admin
  `/orders` endpoint → 403.
- **AC-2** The first `POST /cart/items` creates a Draft. A second add of the same product raises
  its quantity to 2 and creates no second line or Draft. Twenty concurrent first adds from the same
  user end with exactly one Draft.
- **AC-3** Adding more than the stock → 409 `"Only N left in stock"`, cart unchanged. Adding a
  soft-deleted product → 404.
- **AC-4** Placing a 2-line cart: stock decremented by each quantity, lines get fixed price,
  weight, name and SKU, totals match the sum, state `in_progress`, `payment_reference = mock_<number>`,
  one `placed` notification. Changing the product price afterwards doesn't change the order.
- **AC-5** Placing the same `order_id` twice → both 200, same body, stock decremented once, one
  notification.
- **AC-6** **Oversell race:** product with stock 1, two users each with it in their cart, placing at
  the same time → exactly one 200 and one 409 `"Some items in your cart are unavailable"`. Final
  stock is 0.
- **AC-7** **Deadlock check:** two carts holding products A and B, added in opposite orders, placed
  at the same time 50 times → no deadlock errors.
- **AC-8** Admin changes a product's price after the customer loaded the review page → place with
  the old `expected_total` → 409 `"Prices changed…"`. Nothing changed. Placing again with the new
  total → 200.
- **AC-9** A declining gateway double → 402, Draft unchanged, stock unchanged, no notification.
- **AC-10** After placement, the user's next `POST /cart/items` creates a **new** Draft.
- **AC-11** Admin cancel of an `in_progress` order restores stock and writes a `cancelled`
  notification. A second cancel → 409, and stock is restored only once. Cancel and complete
  issued at the same time → one succeeds, the other gets 409.
- **AC-12** Complete or cancel on a `draft`, `completed` or `cancelled` order → 409.
- **AC-13** `GET /users/me/orders` returns only the caller's placed orders. Asking for another
  user's order id → 404.
- **AC-14** Admin `GET /orders/` with no filter excludes Drafts. `?state=draft` lists them.
- **AC-15** The notification task sends one email through Mailpit with the order number, every
  line, the total and the link. Running the task again for the same id sends nothing. With SMTP
  down, each attempt pushes `available_at` back (30 s, 60 s, 120 s, …), and the row ends `failed`
  after 5 attempts.
- **AC-16** Enqueueing broken after the commit (patched): the beat job sends the email within
  3 minutes.
- **AC-17** A product named `<script>alert(1)</script>` appears escaped in the email HTML.
- **AC-18** After placement, `GET /products/{id}` shows the new stock immediately (cache invalidated).

## 8. Open questions / future work

- **Real payment provider.** With network I/O, the charge moves out of the transaction:
  1. A new state, `pending_payment`, with stock taken.
  2. The charge, using the order id as the idempotency key.
  3. `in_progress` on success, or a restock on failure.
  4. A reaper for orders stuck in `pending_payment`.

  `PaymentsGateway` is already the seam for this.
- **Refunds on cancel** once a real provider exists.
- **Abandoned Drafts**: a beat job to soft-delete Drafts untouched for N days.
- **Guest checkout** / a guest cart in localStorage merged at login.
- **Shipping address and shipping cost** (weight-based, using `total_weight`).
- **Customer cancellation** while `in_progress`, maybe within a time window.
- **Order history audit**: an `order_event` table (who changed the state and when) if admins need
  more than the timestamps.
- **Search and export** for the admin orders list (by customer email, order number, date range).
