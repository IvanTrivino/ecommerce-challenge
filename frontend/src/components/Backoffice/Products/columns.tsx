import type { ColumnDef } from "@tanstack/react-table"

import type { ProductPublic } from "@/client"
import { ProductActionsMenu } from "@/components/Backoffice/Products/ProductActionsMenu"
import type { DataTableFeatures } from "@/components/Common/DataTable"
import { ProductImage } from "@/components/Store/ProductImage"
import { useCategories } from "@/hooks/useCategories"
import { formatDate, formatPrice } from "@/lib/format"
import { cn } from "@/lib/utils"

function CategoryCell({ categoryId }: { categoryId: string }) {
  const { categoryName } = useCategories()
  return <span>{categoryName(categoryId)}</span>
}

export const columns: ColumnDef<DataTableFeatures, ProductPublic>[] = [
  {
    id: "image",
    header: () => <span className="sr-only">Image</span>,
    cell: ({ row }) => (
      <ProductImage
        key={row.original.image_url}
        src={row.original.image_url}
        alt=""
        className="size-10 rounded"
      />
    ),
  },
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => (
      <span className="block max-w-xs truncate font-medium">
        {row.original.name}
      </span>
    ),
  },
  {
    accessorKey: "sku",
    header: "SKU",
    cell: ({ row }) => (
      <span className="font-mono text-xs">{row.original.sku}</span>
    ),
  },
  {
    id: "category",
    header: "Category",
    cell: ({ row }) => <CategoryCell categoryId={row.original.category_uuid} />,
  },
  {
    accessorKey: "price",
    header: () => <div className="text-right">Price</div>,
    cell: ({ row }) => (
      <div className="text-right">{formatPrice(row.original.price)}</div>
    ),
  },
  {
    accessorKey: "stock",
    header: "Stock",
    cell: ({ row }) => (
      <span className={cn(!row.original.stock && "text-destructive")}>
        {row.original.stock ?? 0}
      </span>
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
        <ProductActionsMenu product={row.original} />
      </div>
    ),
  },
]
