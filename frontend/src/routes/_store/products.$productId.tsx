import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, Link, notFound } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { ArrowLeft } from "lucide-react"
import { useState } from "react"
import { z } from "zod"

import NotFound from "@/components/Common/NotFound"
import { AddToCartButton } from "@/components/Store/AddToCartButton"
import { ProductImage } from "@/components/Store/ProductImage"
import { StockBadge } from "@/components/Store/StockBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { pageTitle } from "@/config"
import { useCategories } from "@/hooks/useCategories"
import { formatPrice, formatWeight } from "@/lib/format"
import { MAX_QUANTITY_PER_ITEM } from "@/lib/orders"
import { productQueryOptions } from "@/lib/queries/products"

export const Route = createFileRoute("/_store/products/$productId")({
  component: ProductDetail,
  notFoundComponent: NotFound,
  loader: async ({ context, params }) => {
    if (!z.uuid().safeParse(params.productId).success) throw notFound()
    try {
      return await context.queryClient.ensureQueryData(
        productQueryOptions(params.productId),
      )
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        throw notFound()
      }
      throw error
    }
  },
  head: ({ loaderData }) => ({
    meta: [{ title: pageTitle(loaderData?.name ?? "Product") }],
  }),
})

function ProductDetail() {
  const { productId } = Route.useParams()
  const { data: product } = useSuspenseQuery(productQueryOptions(productId))
  const { categoryName, byId } = useCategories()
  const category = byId.get(product.category_uuid)
  const stock = product.stock ?? 0
  const maxQuantity = Math.min(stock, MAX_QUANTITY_PER_ITEM)
  const [quantity, setQuantity] = useState(1)

  return (
    <div className="flex flex-col gap-6">
      <Button variant="ghost" className="w-fit -ml-3" asChild>
        <Link to="/">
          <ArrowLeft />
          Back to products
        </Link>
      </Button>
      <div className="grid gap-8 md:grid-cols-2">
        <ProductImage
          key={product.image_url}
          src={product.image_url}
          alt={product.name}
          className="rounded-lg"
          eager
        />
        <div className="flex flex-col gap-4">
          <div>
            {category ? (
              <Link
                to="/"
                search={{ category: category.id, page: 1 }}
                className="text-sm text-muted-foreground hover:underline"
              >
                {category.name}
              </Link>
            ) : (
              <span className="text-sm text-muted-foreground">
                {categoryName(product.category_uuid)}
              </span>
            )}
            <h1 className="mt-1 text-3xl font-bold tracking-tight break-words">
              {product.name}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-2xl font-semibold">
              {formatPrice(product.price)}
            </span>
            <StockBadge stock={stock} />
          </div>
          <div className="flex items-end gap-3">
            {stock > 0 ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="quantity">Quantity</Label>
                <Input
                  id="quantity"
                  type="number"
                  min={1}
                  max={maxQuantity}
                  value={quantity}
                  className="w-20"
                  onChange={(e) => setQuantity(Number(e.target.value))}
                  onBlur={() =>
                    setQuantity((q) =>
                      Math.min(maxQuantity, Math.max(1, Math.trunc(q) || 1)),
                    )
                  }
                />
              </div>
            ) : null}
            <AddToCartButton
              product={product}
              quantity={Math.min(
                maxQuantity,
                Math.max(1, Math.trunc(quantity) || 1),
              )}
              label="Add to cart"
              size="default"
            />
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">SKU</dt>
            <dd className="font-mono">{product.sku}</dd>
            {product.weight ? (
              <>
                <dt className="text-muted-foreground">Weight</dt>
                <dd>{formatWeight(product.weight)}</dd>
              </>
            ) : null}
          </dl>
          {product.description ? (
            <p className="whitespace-pre-line break-words">
              {product.description}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  )
}
