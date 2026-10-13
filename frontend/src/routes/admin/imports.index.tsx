import { useQuery } from "@tanstack/react-query"
import {
  createFileRoute,
  Link,
  stripSearchParams,
  useNavigate,
} from "@tanstack/react-router"
import { FileUp } from "lucide-react"
import { z } from "zod"
import { columns } from "@/components/Backoffice/Imports/columns"
import { ImportProgress } from "@/components/Backoffice/Imports/ImportProgress"
import { ImportUploadCard } from "@/components/Backoffice/Imports/ImportUploadCard"
import { useImportFinished } from "@/components/Backoffice/Imports/useImportFinished"
import { DataTable } from "@/components/Common/DataTable"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { ADMIN_PAGE_SIZE, pageTitle } from "@/config"
import { isImportActive } from "@/lib/productImports"
import { importListQueryOptions } from "@/lib/queries/productImports"

const importsSearch = z.object({
  page: z.number().int().positive().catch(1).default(1),
})

export const Route = createFileRoute("/admin/imports/")({
  component: Imports,
  search: { middlewares: [stripSearchParams({ page: 1 })] },
  validateSearch: importsSearch,
  head: () => ({
    meta: [{ title: pageTitle("Imports") }],
  }),
})

function Imports() {
  const { page } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const { data, isPending } = useQuery(
    importListQueryOptions(page, ADMIN_PAGE_SIZE),
  )
  const imports = data?.data ?? []
  const activeImport = imports.find((i) => isImportActive(i.status))
  // The newest import is the one that can be active: watching it (not only the
  // active one) is what lets us see it finish
  useImportFinished(page === 1 ? imports[0] : undefined)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Imports</h1>
        <p className="text-muted-foreground">
          Create or update products in bulk from a CSV file
        </p>
      </div>

      {activeImport && (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Import in progress: {activeImport.filename}</CardTitle>
            <Button variant="outline" size="sm" asChild>
              <Link
                to="/admin/imports/$importId"
                params={{ importId: activeImport.id }}
              >
                View details
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            <ImportProgress productImport={activeImport} />
          </CardContent>
        </Card>
      )}

      <ImportUploadCard activeImport={activeImport} />

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">History</h2>
        {isPending ? (
          <Skeleton className="h-32 w-full" />
        ) : imports.length === 0 && page === 1 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-4 rounded-full bg-muted p-4">
              <FileUp className="h-8 w-8 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-semibold">No imports yet</h3>
            <p className="text-muted-foreground">
              Upload a CSV to create or update products
            </p>
          </div>
        ) : (
          <DataTable
            columns={columns}
            data={imports}
            pagination={{
              page,
              pageSize: ADMIN_PAGE_SIZE,
              total: data?.count ?? 0,
              onPageChange: (p) =>
                navigate({ search: (prev) => ({ ...prev, page: p }) }),
            }}
          />
        )}
      </section>
    </div>
  )
}
