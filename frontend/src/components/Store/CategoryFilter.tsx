import { Link } from "@tanstack/react-router"

import { useCategories } from "@/hooks/useCategories"
import { cn } from "@/lib/utils"

const chip =
  "shrink-0 rounded-full border px-3 py-1 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
const activeChip =
  "border-primary bg-primary text-primary-foreground hover:bg-primary/90"

export function CategoryFilter({ selected }: { selected?: string }) {
  const { categories } = useCategories()

  return (
    <nav
      aria-label="Categories"
      className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0"
      data-testid="category-filter"
    >
      <Link
        to="/"
        search={{ page: 1 }}
        aria-current={selected ? undefined : "true"}
        className={cn(chip, !selected && activeChip)}
      >
        All
      </Link>
      {categories.map((category) => (
        <Link
          key={category.id}
          to="/"
          search={{ category: category.id, page: 1 }}
          aria-current={selected === category.id ? "true" : undefined}
          className={cn(chip, selected === category.id && activeChip)}
        >
          {category.name}
        </Link>
      ))}
    </nav>
  )
}
