import { Link } from "@tanstack/react-router"

import type { ProductPublic } from "@/client"
import { ProductImagePlaceholder } from "@/components/Store/ProductImagePlaceholder"
import { StockBadge } from "@/components/Store/StockBadge"
import { useCategories } from "@/hooks/useCategories"
import { formatPrice } from "@/lib/format"

export function ProductCard({ product }: { product: ProductPublic }) {
  const { categoryName } = useCategories()

  return (
    <Link
      to="/products/$productId"
      params={{ productId: product.id }}
      data-testid="product-card"
      className="group flex flex-col overflow-hidden rounded-lg border bg-card transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      <ProductImagePlaceholder />
      <div className="flex flex-1 flex-col gap-2 p-4">
        <span className="text-xs text-muted-foreground">
          {categoryName(product.category_uuid)}
        </span>
        <h3 className="line-clamp-2 font-medium leading-snug group-hover:underline">
          {product.name}
        </h3>
        <div className="mt-auto flex items-center justify-between gap-2 pt-2">
          <span className="font-semibold">{formatPrice(product.price)}</span>
          <StockBadge stock={product.stock ?? 0} />
        </div>
      </div>
    </Link>
  )
}
