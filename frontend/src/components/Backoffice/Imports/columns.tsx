import { Link } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"

import type { ProductImportPublic } from "@/client"
import { ImportStatusBadge } from "@/components/Backoffice/Imports/ImportStatusBadge"
import type { DataTableFeatures } from "@/components/Common/DataTable"
import { formatDate } from "@/lib/format"

const number = (field: keyof ProductImportPublic, header: string) =>
  ({
    id: field,
    header: () => <div className="text-right">{header}</div>,
    cell: ({ row }) => (
      <div className="text-right tabular-nums">{`${row.original[field]}`}</div>
    ),
  }) satisfies ColumnDef<DataTableFeatures, ProductImportPublic>

export const columns: ColumnDef<DataTableFeatures, ProductImportPublic>[] = [
  {
    accessorKey: "created_at",
    header: "Started",
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {formatDate(row.original.created_at)}
      </span>
    ),
  },
  {
    accessorKey: "filename",
    header: "File",
    cell: ({ row }) => (
      <Link
        to="/admin/imports/$importId"
        params={{ importId: row.original.id }}
        className="block max-w-xs truncate font-medium underline-offset-4 hover:underline"
      >
        {row.original.filename}
      </Link>
    ),
  },
  {
    id: "by",
    header: "By",
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {row.original.created_by_email ?? "—"}
      </span>
    ),
  },
  {
    id: "status",
    header: "Status",
    cell: ({ row }) => <ImportStatusBadge productImport={row.original} />,
  },
  {
    id: "progress",
    header: "Progress",
    cell: ({ row }) => (
      <span className="tabular-nums">{row.original.progress}%</span>
    ),
  },
  number("created_count", "Created"),
  number("updated_count", "Updated"),
  number("error_count", "Errors"),
]
