import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, notFound } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { ArrowLeft, RotateCw } from "lucide-react"
import { z } from "zod"

import { ProductImportsService } from "@/client"
import { ImportErrorsTable } from "@/components/Backoffice/Imports/ImportErrorsTable"
import { ImportProgress } from "@/components/Backoffice/Imports/ImportProgress"
import { useImportFinished } from "@/components/Backoffice/Imports/useImportFinished"
import NotFound from "@/components/Common/NotFound"
import { Button } from "@/components/ui/button"
import { LoadingButton } from "@/components/ui/loading-button"
import { pageTitle } from "@/config"
import useCustomToast from "@/hooks/useCustomToast"
import { formatDate } from "@/lib/format"
import { isImportActive } from "@/lib/productImports"
import { importKeys, importQueryOptions } from "@/lib/queries/productImports"
import { handleError } from "@/utils"

export const Route = createFileRoute("/admin/imports/$importId")({
  component: ImportDetail,
  notFoundComponent: NotFound,
  loader: async ({ context, params }) => {
    if (!z.uuid().safeParse(params.importId).success) throw notFound()
    try {
      return await context.queryClient.ensureQueryData(
        importQueryOptions(params.importId),
      )
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404)
        throw notFound()
      throw error
    }
  },
  head: ({ loaderData }) => ({
    meta: [{ title: pageTitle(loaderData?.filename ?? "Import") }],
  }),
})

function ImportDetail() {
  const { importId } = Route.useParams()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()
  // Not suspense: polling updates must re-render without suspending
  const { data } = useQuery(importQueryOptions(importId))
  useImportFinished(data)

  const retry = useMutation({
    mutationFn: async () =>
      (
        await ProductImportsService.retryProductImport({
          path: { import_id: importId },
        })
      ).data,
    onSuccess: () => {
      // Polling resumes from the refetched (pending) status
      queryClient.invalidateQueries({ queryKey: importKeys.detail(importId) })
      queryClient.invalidateQueries({ queryKey: importKeys.all })
    },
    onError: handleError.bind(showErrorToast),
  })

  if (!data) return null

  return (
    <div className="flex flex-col gap-6">
      <Button variant="ghost" className="w-fit -ml-3" asChild>
        <Link to="/admin/imports">
          <ArrowLeft />
          Back to imports
        </Link>
      </Button>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-bold tracking-tight">
            {data.filename}
          </h1>
          <p className="text-muted-foreground">
            Started {formatDate(data.created_at)} by{" "}
            {data.created_by_email ?? "an unknown user"}
          </p>
        </div>
        {data.can_retry && (
          <LoadingButton
            loading={retry.isPending}
            onClick={() => retry.mutate()}
          >
            <RotateCw />
            Retry
          </LoadingButton>
        )}
      </div>
      <ImportProgress productImport={data} />
      {!isImportActive(data.status) && (
        <ImportErrorsTable productImport={data} />
      )}
    </div>
  )
}
