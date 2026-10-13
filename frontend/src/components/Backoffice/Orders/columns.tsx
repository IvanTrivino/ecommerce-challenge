import { Link } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"

import type { OrderSummaryPublic } from "@/client"
import { OrderRowActions } from "@/components/Backoffice/Orders/OrderRowActions"
import type { DataTableFeatures } from "@/components/Common/DataTable"
import { OrderStateBadge } from "@/components/Orders/OrderStateBadge"
import { formatDate, formatPrice, formatWeight } from "@/lib/format"

export const columns: ColumnDef<DataTableFeatures, OrderSummaryPublic>[] = [
  {
    id: "number",
    header: "Order",
    cell: ({ row }) => (
      <Link
        to="/admin/orders/$orderId"
        params={{ orderId: row.original.id }}
        className="font-mono font-medium underline-offset-4 hover:underline"
      >
        #{row.original.number}
      </Link>
    ),
  },
  {
    accessorKey: "user_email",
    header: "Customer",
    cell: ({ row }) => (
      <span className="block max-w-48 truncate text-muted-foreground">
        {row.original.user_email}
      </span>
    ),
  },
  {
    accessorKey: "placed_at",
    header: "Placed",
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {row.original.placed_at ? formatDate(row.original.placed_at) : "—"}
      </span>
    ),
  },
  {
    accessorKey: "item_count",
    header: () => <div className="text-right">Items</div>,
    cell: ({ row }) => (
      <div className="text-right tabular-nums">{row.original.item_count}</div>
    ),
  },
  {
    accessorKey: "total_weight",
    header: () => <div className="text-right">Weight</div>,
    cell: ({ row }) => (
      <div className="text-right tabular-nums">
        {row.original.total_weight
          ? formatWeight(row.original.total_weight)
          : "—"}
      </div>
    ),
  },
  {
    accessorKey: "total_price",
    header: () => <div className="text-right">Total</div>,
    cell: ({ row }) => (
      <div className="text-right tabular-nums">
        {row.original.total_price ? formatPrice(row.original.total_price) : "—"}
      </div>
    ),
  },
  {
    accessorKey: "state",
    header: "State",
    cell: ({ row }) => <OrderStateBadge state={row.original.state} />,
  },
  {
    id: "actions",
    header: () => <span className="sr-only">Actions</span>,
    cell: ({ row }) => <OrderRowActions order={row.original} />,
  },
]
