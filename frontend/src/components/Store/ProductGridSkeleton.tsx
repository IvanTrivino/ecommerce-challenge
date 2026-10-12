import { GRID_CLASS } from "@/components/Store/ProductGrid"
import { Skeleton } from "@/components/ui/skeleton"
import { STORE_PAGE_SIZE } from "@/config"

export function ProductGridSkeleton() {
  return (
    <div className={GRID_CLASS} aria-busy="true">
      {Array.from({ length: STORE_PAGE_SIZE }).map((_, index) => (
        <div key={index} className="overflow-hidden rounded-lg border">
          <Skeleton className="aspect-square w-full rounded-none" />
          <div className="flex flex-col gap-2 p-4">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-5 w-full" />
            <div className="flex items-center justify-between pt-2">
              <Skeleton className="h-5 w-16" />
              <Skeleton className="h-5 w-20 rounded-full" />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
