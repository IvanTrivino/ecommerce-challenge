import { Link } from "@tanstack/react-router"

import type { ProductPublic } from "@/client"
import { AddToCartButton } from "@/components/Store/AddToCartButton"
import { ProductImage } from "@/components/Store/ProductImage"
import { StockBadge } from "@/components/Store/StockBadge"
import { useCategories } from "@/hooks/useCategories"
import { formatPrice } from "@/lib/format"

// The link's ::after stretches over the card so all of it stays clickable,
// while the button sits above it as a sibling (a button can't live inside an anchor)
export function ProductCard({ product }: { product: ProductPublic }) {
  const { categoryName } = useCategories()

  return (
    <article
      data-testid="product-card"
      className="group relative flex flex-col overflow-hidden rounded-lg border bg-card transition-shadow hover:shadow-md has-[a:focus-visible]:ring-[3px] has-[a:focus-visible]:ring-ring/50"
    >
      <ProductImage key={product.image_url} src={product.image_url} alt="" />
      <div className="flex flex-1 flex-col gap-2 p-4">
        <span className="text-xs text-muted-foreground">
          {categoryName(product.category_uuid)}
        </span>
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
        <AddToCartButton
          product={product}
          className="relative z-10 mt-2 w-full"
        />
      </div>
    </article>
  )
}
