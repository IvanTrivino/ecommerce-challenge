import { createFileRoute } from "@tanstack/react-router"
import { Tags } from "lucide-react"

import AddCategory from "@/components/Backoffice/Categories/AddCategory"
import { columns } from "@/components/Backoffice/Categories/columns"
import { DataTable } from "@/components/Common/DataTable"
import { pageTitle } from "@/config"
import { useCategories } from "@/hooks/useCategories"

export const Route = createFileRoute("/admin/categories")({
  component: Categories,
  head: () => ({
    meta: [{ title: pageTitle("Categories") }],
  }),
})

function Categories() {
  const { categories } = useCategories()

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Categories</h1>
          <p className="text-muted-foreground">Manage product categories</p>
        </div>
        <AddCategory />
      </div>
      {categories.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="mb-4 rounded-full bg-muted p-4">
            <Tags className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold">No categories yet</h3>
          <p className="text-muted-foreground">Add a category to get started</p>
        </div>
      ) : (
        <DataTable columns={columns} data={categories} />
      )}
    </div>
  )
}
