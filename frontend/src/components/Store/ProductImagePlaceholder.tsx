import { Package } from "lucide-react"

import { cn } from "@/lib/utils"

export function ProductImagePlaceholder({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex aspect-square w-full items-center justify-center bg-muted text-muted-foreground",
        className,
      )}
    >
      <Package className="size-1/4" aria-hidden />
    </div>
  )
}
