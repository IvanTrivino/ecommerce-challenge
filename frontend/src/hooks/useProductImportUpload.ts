import axios from "axios"
import { useCallback, useEffect, useRef, useState } from "react"

import { ProductImportsService } from "@/client"
import {
  importStorageErrorMessage,
  validateCsvFile,
} from "@/lib/productImports"
import { uploadToStorage } from "@/lib/storageUpload"
import { extractErrorMessage } from "@/utils"

export type ImportUploadState =
  | { status: "idle" }
  | { status: "uploading"; progress: number; file: File }
  | { status: "uploaded"; key: string; filename: string; size: number }
  | { status: "error"; message: string }

export function useProductImportUpload() {
  const [state, setState] = useState<ImportUploadState>({ status: "idle" })
  const controllerRef = useRef<AbortController | null>(null)

  const clear = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
  }, [])

  const reset = useCallback(() => {
    clear()
    setState({ status: "idle" })
  }, [clear])

  const start = useCallback(
    async (file: File) => {
      // Invalid files never reach the network
      const invalid = validateCsvFile(file)
      if (invalid) {
        clear()
        setState({ status: "error", message: invalid })
        return
      }

      clear()
      const controller = new AbortController()
      const { signal } = controller
      controllerRef.current = controller
      setState({ status: "uploading", progress: 0, file })

      let presigned = false
      try {
        const { data } = await ProductImportsService.presignProductImport({
          body: { filename: file.name, size: file.size },
          signal,
        })
        presigned = true
        await uploadToStorage(data, file, {
          signal,
          onProgress: (progress) => {
            if (!signal.aborted)
              setState({ status: "uploading", progress, file })
          },
        })
        if (signal.aborted) return
        setState({
          status: "uploaded",
          key: data.key,
          filename: file.name,
          size: file.size,
        })
      } catch (err) {
        if (signal.aborted || axios.isCancel(err)) return
        const message = presigned
          ? importStorageErrorMessage(err)
          : extractErrorMessage(err as Error)
        setState({ status: "error", message })
      }
    },
    [clear],
  )

  useEffect(() => clear, [clear])

  return { state, isUploading: state.status === "uploading", start, reset }
}
