import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef } from "react"

import type { ProductImportPublic } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import {
  type ImportStatus,
  importSummary,
  isImportActive,
} from "@/lib/productImports"
import { categoryKeys } from "@/lib/queries/categories"
import { importKeys } from "@/lib/queries/productImports"
import { productKeys } from "@/lib/queries/products"

// Reacts to the transition seen while polling. Opening an import that already
// finished does not toast
export function useImportFinished(
  productImport: ProductImportPublic | undefined,
) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const previous = useRef<ImportStatus | undefined>(undefined)
  const status = productImport?.status

  useEffect(() => {
    const wasActive = isImportActive(previous.current)
    previous.current = status
    if (!productImport || !wasActive || isImportActive(status)) return

    queryClient.invalidateQueries({ queryKey: productKeys.all })
    queryClient.invalidateQueries({ queryKey: categoryKeys.all })
    queryClient.invalidateQueries({ queryKey: importKeys.all })
    if (status === "completed")
      showSuccessToast(`Import finished: ${importSummary(productImport)}`)
    else showErrorToast(productImport.error_message ?? "Import failed")
  }, [status, productImport, queryClient, showSuccessToast, showErrorToast])
}
