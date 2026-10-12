import type { ReactNode } from "react"

import type { ProductPublic } from "@/client"
import { ProductCard } from "@/components/Store/ProductCard"

export const GRID_CLASS =
  "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"

interface ProductGridProps {
  products: ProductPublic[]
  empty: ReactNode
}

export function ProductGrid({ products, empty }: ProductGridProps) {
  if (products.length === 0) {
    return (
      <div
        className="flex flex-col items-center gap-3 py-16 text-center"
        data-testid="product-grid-empty"
      >
        {empty}
      </div>
    )
  }

  return (
    <div className={GRID_CLASS} data-testid="product-grid">
      {products.map((product) => (
        <ProductCard key={product.id} product={product} />
      ))}
    </div>
  )
}
