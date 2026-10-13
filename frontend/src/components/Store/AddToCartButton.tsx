import { Plus } from "lucide-react"

import type { ProductPublic } from "@/client"
import { LoadingButton } from "@/components/ui/loading-button"
import { useAddToCart } from "@/hooks/useAddToCart"

type Props = {
  product: ProductPublic
  quantity?: number
  label?: string
  className?: string
  size?: "default" | "sm" | "lg"
}

export function AddToCartButton({
  product,
  quantity = 1,
  label = "Add",
  className,
  size = "sm",
}: Props) {
  const { add, isPending } = useAddToCart()
  const soldOut = (product.stock ?? 0) <= 0

  return (
    <LoadingButton
      size={size}
      className={className}
      loading={isPending}
      disabled={soldOut}
      onClick={() =>
        add({ productId: product.id, quantity, name: product.name })
      }
      aria-label={
        soldOut ? `${product.name} is sold out` : `Add ${product.name} to cart`
      }
      data-testid="add-to-cart"
    >
      {soldOut ? (
        "Sold out"
      ) : (
        <>
          <Plus aria-hidden /> {label}
        </>
      )}
    </LoadingButton>
  )
}
