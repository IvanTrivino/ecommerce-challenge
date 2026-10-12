import { Badge } from "@/components/ui/badge"
import { LOW_STOCK_THRESHOLD } from "@/config"

export function StockBadge({ stock }: { stock: number }) {
  if (stock <= 0) {
    return <Badge variant="destructive">Out of stock</Badge>
  }
  if (stock <= LOW_STOCK_THRESHOLD) {
    return <Badge variant="outline">Only {stock} left</Badge>
  }
  return <Badge variant="secondary">In stock</Badge>
}
