import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"

interface PaginationBarProps {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
}

// First, last and the current page with its neighbours; null marks a gap
function visiblePages(page: number, last: number): (number | null)[] {
  const pages = [
    ...new Set(
      [1, page - 1, page, page + 1, last].filter((p) => p >= 1 && p <= last),
    ),
  ].sort((a, b) => a - b)
  const result: (number | null)[] = []
  pages.forEach((p, i) => {
    if (i > 0 && p - pages[i - 1] > 1) result.push(null)
    result.push(p)
  })
  return result
}

export function PaginationBar({
  page,
  pageSize,
  total,
  onPageChange,
}: PaginationBarProps) {
  const last = Math.ceil(total / pageSize)
  if (total <= pageSize) return null

  const go = (target: number) => (e: React.MouseEvent) => {
    e.preventDefault()
    if (target >= 1 && target <= last && target !== page) onPageChange(target)
  }

  return (
    <Pagination data-testid="pagination">
      <PaginationContent>
        <PaginationItem>
          <PaginationPrevious
            href="#"
            onClick={go(page - 1)}
            aria-disabled={page <= 1}
            className={page <= 1 ? "pointer-events-none opacity-50" : undefined}
          />
        </PaginationItem>
        {visiblePages(page, last).map((p, i) =>
          p === null ? (
            <PaginationItem key={`gap-${i}`}>
              <PaginationEllipsis />
            </PaginationItem>
          ) : (
            <PaginationItem key={p}>
              <PaginationLink
                href="#"
                isActive={p === page}
                onClick={go(p)}
                aria-label={`Go to page ${p}`}
              >
                {p}
              </PaginationLink>
            </PaginationItem>
          ),
        )}
        <PaginationItem>
          <PaginationNext
            href="#"
            onClick={go(page + 1)}
            aria-disabled={page >= last}
            className={
              page >= last ? "pointer-events-none opacity-50" : undefined
            }
          />
        </PaginationItem>
      </PaginationContent>
    </Pagination>
  )
}
