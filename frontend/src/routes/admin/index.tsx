import { useQuery } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { Package, Tags, Users } from "lucide-react"
import type { ComponentType } from "react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { pageTitle } from "@/config"
import useAuth from "@/hooks/useAuth"
import { useCategories } from "@/hooks/useCategories"
import { productListQueryOptions } from "@/lib/queries/products"
import { usersCountQueryOptions } from "@/lib/queries/users"

export const Route = createFileRoute("/admin/")({
  component: Overview,
  head: () => ({
    meta: [{ title: pageTitle("Overview") }],
  }),
})

interface StatCardProps {
  title: string
  to: "/admin/products" | "/admin/categories" | "/admin/users"
  icon: ComponentType<{ className?: string }>
  count?: number
  testId: string
}

function StatCard({ title, to, icon: Icon, count, testId }: StatCardProps) {
  return (
    <Link to={to} data-testid={testId}>
      <Card className="transition-colors hover:bg-accent/50">
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-sm font-medium">{title}</CardTitle>
          <Icon className="size-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          {count === undefined ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <p className="text-3xl font-bold">{count}</p>
          )}
        </CardContent>
      </Card>
    </Link>
  )
}

function Overview() {
  const { user } = useAuth()
  const { categories } = useCategories()
  const products = useQuery(productListQueryOptions({ page: 1, pageSize: 1 }))
  const users = useQuery(usersCountQueryOptions)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="max-w-sm truncate text-2xl">
          Hi, {user?.full_name || user?.email} 👋
        </h1>
        <p className="text-muted-foreground">
          Here's what's in your store right now.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          title="Products"
          to="/admin/products"
          icon={Package}
          count={products.data?.count}
          testId="stat-products"
        />
        <StatCard
          title="Categories"
          to="/admin/categories"
          icon={Tags}
          count={categories.length}
          testId="stat-categories"
        />
        <StatCard
          title="Users"
          to="/admin/users"
          icon={Users}
          count={users.data}
          testId="stat-users"
        />
      </div>
    </div>
  )
}
