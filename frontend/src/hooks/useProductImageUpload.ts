import axios from "axios"
import { useCallback, useEffect, useRef, useState } from "react"

import { ProductsService } from "@/client"
import { storageErrorMessage, validateImageFile } from "@/lib/productImages"
import { uploadToStorage } from "@/lib/storageUpload"
import { extractErrorMessage } from "@/utils"

type UploadState =
  | { status: "idle" }
  | { status: "uploading"; progress: number; previewUrl: string }
  | { status: "done"; previewUrl: string }
  | { status: "error"; message: string }

export function useProductImageUpload(onUploaded: (key: string) => void) {
  const [state, setState] = useState<UploadState>({ status: "idle" })
  const controllerRef = useRef<AbortController | null>(null)
  const previewRef = useRef<string | null>(null)
  const onUploadedRef = useRef(onUploaded)
  onUploadedRef.current = onUploaded

  const clear = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    previewRef.current = null
  }, [])

  const reset = useCallback(() => {
    clear()
    setState({ status: "idle" })
  }, [clear])

  const start = useCallback(
    async (file: File) => {
      const invalid = validateImageFile(file)
      if (invalid) {
        setState({ status: "error", message: invalid })
        return
      }

      clear()
      const controller = new AbortController()
      const { signal } = controller
      controllerRef.current = controller
      const previewUrl = URL.createObjectURL(file)
      previewRef.current = previewUrl
      setState({ status: "uploading", progress: 0, previewUrl })

      let presigned = false
      try {
        const { data } = await ProductsService.presignProductImage({
          body: {
            content_type: file.type as
              | "image/jpeg"
              | "image/png"
              | "image/webp",
            size: file.size,
          },
          signal,
        })
        presigned = true
        await uploadToStorage(data, file, {
          signal,
          onProgress: (progress) => {
            if (!signal.aborted)
              setState({ status: "uploading", progress, previewUrl })
          },
        })
        if (signal.aborted) return
        setState({ status: "done", previewUrl })
        onUploadedRef.current(data.key)
      } catch (err) {
        if (signal.aborted || axios.isCancel(err)) return
        const message = presigned
          ? storageErrorMessage(err)
          : extractErrorMessage(err as Error)
        setState({ status: "error", message })
      }
    },
    [clear],
  )

  useEffect(() => clear, [clear])

  return { state, isUploading: state.status === "uploading", start, reset }
}
