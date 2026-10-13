import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { FileUp } from "lucide-react"
import { useState } from "react"

import { type ProductImportPublic, ProductImportsService } from "@/client"
import { ProgressBar } from "@/components/Common/ProgressBar"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { useProductImportUpload } from "@/hooks/useProductImportUpload"
import { formatBytes } from "@/lib/format"
import {
  IMPORT_ACCEPT,
  IMPORT_HINT,
  IMPORT_TEMPLATE_URL,
} from "@/lib/productImports"
import { importKeys } from "@/lib/queries/productImports"
import { handleError } from "@/utils"

const IN_PROGRESS = "Another import is in progress"

export function ImportUploadCard({
  activeImport,
}: {
  activeImport: ProductImportPublic | undefined
}) {
  const upload = useProductImportUpload()
  const { state } = upload
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { showErrorToast } = useCustomToast()
  const [conflict, setConflict] = useState(false)

  const mutation = useMutation({
    mutationFn: async () => {
      if (state.status !== "uploaded") throw new Error("Nothing to import")
      return (
        await ProductImportsService.startProductImport({
          body: { key: state.key, filename: state.filename },
        })
      ).data
    },
    onSuccess: (data) => {
      upload.reset()
      queryClient.invalidateQueries({ queryKey: importKeys.all })
      navigate({
        to: "/admin/imports/$importId",
        params: { importId: data.id },
      })
    },
    onError: (err) => {
      if (err instanceof AxiosError && err.response?.status === 409)
        setConflict(true)
      else handleError.call(showErrorToast, err)
    },
  })

  const pick = (file: File | undefined) => {
    if (!file) return
    setConflict(false)
    void upload.start(file)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload a CSV</CardTitle>
        <CardDescription>
          Columns: name, sku, description, category, price, stock, weight_kg
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {(state.status === "idle" || state.status === "error") && (
          <>
            <label
              htmlFor="import-file"
              data-testid="import-dropzone"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault()
                pick(e.dataTransfer.files[0])
              }}
              className="flex cursor-pointer flex-col items-center gap-2 rounded-md border-2 border-dashed p-8 text-center text-sm text-muted-foreground hover:bg-muted/50 focus-within:ring-[3px] focus-within:ring-ring/50"
            >
              <FileUp className="size-6" />
              Drop a CSV here or click to choose
              <input
                id="import-file"
                type="file"
                accept={IMPORT_ACCEPT}
                aria-label="CSV file"
                className="sr-only"
                data-testid="import-file-input"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  e.target.value = "" // allow re-picking the same file
                  pick(file)
                }}
              />
            </label>
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>{IMPORT_HINT}</span>
              <a
                href={IMPORT_TEMPLATE_URL}
                download
                className="underline underline-offset-4"
              >
                Download template
              </a>
            </div>
            {state.status === "error" && (
              <p role="alert" className="text-sm text-destructive">
                {state.message}
              </p>
            )}
          </>
        )}

        {state.status === "uploading" && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2 text-sm">
              <span className="truncate font-medium">{state.file.name}</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={upload.reset}
              >
                Cancel
              </Button>
            </div>
            <ProgressBar value={state.progress} label="Upload progress" />
          </div>
        )}

        {state.status === "uploaded" && (
          <div className="flex flex-col gap-3">
            <p className="text-sm">
              <span className="font-medium">{state.filename}</span>{" "}
              <span className="text-muted-foreground">
                ({formatBytes(state.size)})
              </span>
            </p>
            <div className="flex flex-wrap gap-2">
              <LoadingButton
                loading={mutation.isPending}
                disabled={!!activeImport}
                onClick={() => mutation.mutate()}
              >
                Import
              </LoadingButton>
              <Button type="button" variant="outline" onClick={upload.reset}>
                Choose another file
              </Button>
            </div>
            {(conflict || activeImport) && (
              <p role="alert" className="text-sm text-muted-foreground">
                {IN_PROGRESS}.{" "}
                {activeImport && (
                  <Link
                    to="/admin/imports/$importId"
                    params={{ importId: activeImport.id }}
                    className="underline underline-offset-4"
                  >
                    View it
                  </Link>
                )}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
