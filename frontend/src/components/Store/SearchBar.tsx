import { useNavigate, useRouterState } from "@tanstack/react-router"
import { Search } from "lucide-react"
import { useEffect, useState } from "react"

import { Input } from "@/components/ui/input"

export function SearchBar() {
  const navigate = useNavigate()
  const currentQ = useRouterState({
    select: (s) =>
      s.location.pathname === "/search" &&
      typeof s.location.search.q === "string"
        ? s.location.search.q
        : "",
  })
  const [value, setValue] = useState(currentQ)

  useEffect(() => {
    setValue(currentQ)
  }, [currentQ])

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const q = value.trim()
    if (!q) return
    navigate({ to: "/search", search: { q, page: 1 } })
  }

  return (
    <search className="block w-full">
      <form onSubmit={onSubmit} className="relative w-full">
        <Search
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          data-testid="search-input"
          type="search"
          aria-label="Search products"
          placeholder="Search products"
          className="pl-9"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      </form>
    </search>
  )
}
