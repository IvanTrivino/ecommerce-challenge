import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, Link, notFound } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { ArrowLeft } from "lucide-react"
import { z } from "zod"

import NotFound from "@/components/Common/NotFound"
import { ProductImagePlaceholder } from "@/components/Store/ProductImagePlaceholder"
import { StockBadge } from "@/components/Store/StockBadge"
import { Button } from "@/components/ui/button"
import { pageTitle } from "@/config"
import { useCategories } from "@/hooks/useCategories"
import { formatPrice, formatWeight } from "@/lib/format"
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

  return (
    <div className="flex flex-col gap-6">
      <Button variant="ghost" className="w-fit -ml-3" asChild>
        <Link to="/">
          <ArrowLeft />
          Back to products
        </Link>
      </Button>
      <div className="grid gap-8 md:grid-cols-2">
        <ProductImagePlaceholder className="rounded-lg" />
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
            <StockBadge stock={product.stock ?? 0} />
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
