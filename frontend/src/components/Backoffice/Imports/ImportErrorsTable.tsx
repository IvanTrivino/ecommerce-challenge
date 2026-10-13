import { useQuery } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"
import { Download } from "lucide-react"
import { useState } from "react"

import type { ProductImportPublic } from "@/client"
import type { DataTableFeatures } from "@/components/Common/DataTable"
import { DataTable } from "@/components/Common/DataTable"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { buildErrorReport } from "@/lib/productImports"
import {
  fetchAllImportErrors,
  importErrorsQueryOptions,
} from "@/lib/queries/productImports"
import { handleError } from "@/utils"

const PAGE_SIZE = 50

type ErrorRow = { line: number; sku: string | null; message: string }

const columns: ColumnDef<DataTableFeatures, ErrorRow>[] = [
  { accessorKey: "line", header: "Line" },
  {
    accessorKey: "sku",
    header: "SKU",
    cell: ({ row }) => (
      <span className="font-mono text-xs">{row.original.sku ?? "—"}</span>
    ),
  },
  { accessorKey: "message", header: "Error" },
]

export function ImportErrorsTable({
  productImport,
}: {
  productImport: ProductImportPublic
}) {
  const [page, setPage] = useState(1)
  const [downloading, setDownloading] = useState(false)
  const { showErrorToast } = useCustomToast()
  const { data } = useQuery(
    importErrorsQueryOptions(productImport.id, page, PAGE_SIZE),
  )

  const download = async () => {
    setDownloading(true)
    try {
      const rows = await fetchAllImportErrors(productImport.id)
      const blob = new Blob([buildErrorReport(rows)], {
        type: "text/csv;charset=utf-8",
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.download = `import-${productImport.id}-errors.csv`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      handleError.call(showErrorToast, err as Error)
    } finally {
      setDownloading(false)
    }
  }

  if (!data) return null
  if (data.count === 0)
    return (
      <p className="text-sm text-muted-foreground">No rows were rejected</p>
    )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Rejected rows</h2>
        <LoadingButton
          variant="outline"
          loading={downloading}
          onClick={download}
          data-testid="download-error-report"
        >
          <Download />
          Download error report
        </LoadingButton>
      </div>
      {data.truncated && (
        <p className="text-sm text-muted-foreground">
          Showing the first {data.count} of {productImport.error_count} errors.
        </p>
      )}
      <DataTable
        columns={columns}
        data={data.data}
        pagination={{
          page,
          pageSize: PAGE_SIZE,
          total: data.count,
          onPageChange: setPage,
        }}
      />
    </div>
  )
}
