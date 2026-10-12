import { useState } from "react"

import { ProductImagePlaceholder } from "@/components/Store/ProductImagePlaceholder"
import { cn } from "@/lib/utils"

// Call sites pass `key={src}` so a new `src` gets a fresh failure state
export function ProductImage({
  src,
  alt,
  className,
  eager = false,
}: {
  src: string | null | undefined
  alt: string
  className?: string
  eager?: boolean
}) {
  const [failed, setFailed] = useState(false)

  if (!src || failed) return <ProductImagePlaceholder className={className} />
  return (
    <img
      src={src}
      alt={alt}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      fetchPriority={eager ? "high" : undefined}
      onError={() => setFailed(true)}
      data-testid="product-image"
      className={cn("aspect-square w-full bg-muted object-cover", className)}
    />
  )
}
