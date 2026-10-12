import type { ColumnDef } from "@tanstack/react-table"

import type { ProductCategoryPublic } from "@/client"
import { CategoryActionsMenu } from "@/components/Backoffice/Categories/CategoryActionsMenu"
import type { DataTableFeatures } from "@/components/Common/DataTable"
import { formatDate } from "@/lib/format"

export const columns: ColumnDef<DataTableFeatures, ProductCategoryPublic>[] = [
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
  },
  {
    accessorKey: "code",
    header: "Code",
    cell: ({ row }) => (
      <span className="font-mono text-xs">{row.original.code}</span>
    ),
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {formatDate(row.original.created_at)}
      </span>
    ),
  },
  {
    id: "actions",
    header: () => <span className="sr-only">Actions</span>,
    cell: ({ row }) => (
      <div className="flex justify-end">
        <CategoryActionsMenu category={row.original} />
      </div>
    ),
  },
]
