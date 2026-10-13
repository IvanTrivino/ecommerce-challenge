import type { OrderPublic } from "@/client"
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatPrice, formatWeight } from "@/lib/format"

const money = (value: string | null) => (value ? formatPrice(value) : "—")

export function OrderItemsTable({ order }: { order: OrderPublic }) {
  const priced = order.total_price !== null
  return (
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
        {order.items.map((item) => (
          <TableRow key={item.id} data-testid="order-line">
            <TableCell className="whitespace-normal">
              <div className="font-medium break-words">{item.name}</div>
              <div className="font-mono text-xs text-muted-foreground">
                {item.sku}
              </div>
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {item.quantity}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {money(item.unit_price)}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {money(item.line_total)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
      {priced ? (
        <TableFooter>
          <TableRow>
            <TableCell colSpan={3}>Total weight</TableCell>
            <TableCell className="text-right tabular-nums">
              {order.total_weight ? formatWeight(order.total_weight) : "—"}
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell colSpan={3} className="font-semibold">
              Total
            </TableCell>
            <TableCell
              className="text-right font-semibold tabular-nums"
              data-testid="order-total"
            >
              {money(order.total_price)}
            </TableCell>
          </TableRow>
        </TableFooter>
      ) : null}
    </Table>
  )
}
