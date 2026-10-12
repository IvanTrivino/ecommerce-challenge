import { useEffect, useRef } from "react"
import type { UseFormReturn } from "react-hook-form"

import type { ProductFormValues } from "@/components/Backoffice/Products/productSchema"
import { ProductImagePlaceholder } from "@/components/Store/ProductImagePlaceholder"
import { Button } from "@/components/ui/button"
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import type { useProductImageUpload } from "@/hooks/useProductImageUpload"
import { IMAGE_ACCEPT, IMAGE_HINT } from "@/lib/productImages"

interface ProductImageFieldProps {
  form: UseFormReturn<ProductFormValues>
  upload: ReturnType<typeof useProductImageUpload>
  // The saved image (edit), null on create
  currentImageUrl: string | null
  savedImageKey: string
}

export function ProductImageField({
  form,
  upload,
  currentImageUrl,
  savedImageKey,
}: ProductImageFieldProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const { state } = upload
  const imageKey = form.watch("image_key")

  useEffect(() => {
    if (state.status === "error")
      form.setError("image_key", { type: "upload", message: state.message })
    else if (state.status === "uploading") form.clearErrors("image_key")
  }, [state, form])

  const previewUrl =
    state.status === "uploading" || state.status === "done"
      ? state.previewUrl
      : imageKey && imageKey === savedImageKey
        ? currentImageUrl
        : null

  return (
    <FormField
      control={form.control}
      name="image_key"
      render={() => (
        <FormItem>
          <FormLabel>Image</FormLabel>
          <div className="flex items-center gap-4">
            <div
              data-testid="product-image-preview"
              className="size-24 shrink-0 overflow-hidden rounded-md border"
            >
              {previewUrl ? (
                <img
                  src={previewUrl}
                  alt="Preview"
                  className="size-full object-cover"
                />
              ) : (
                <ProductImagePlaceholder />
              )}
            </div>
            <div className="grid min-w-0 flex-1 gap-2">
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => inputRef.current?.click()}
                >
                  {previewUrl ? "Replace" : "Upload image"}
                </Button>
                {previewUrl && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      upload.reset()
                      form.setValue("image_key", "", { shouldDirty: true })
                    }}
                  >
                    Remove
                  </Button>
                )}
              </div>
              {state.status === "uploading" && (
                <div
                  role="progressbar"
                  aria-label="Upload progress"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={state.progress}
                  className="h-1.5 w-full rounded bg-muted"
                >
                  <div
                    className="h-full rounded bg-primary transition-[width]"
                    style={{ width: `${state.progress}%` }}
                  />
                </div>
              )}
              <FormDescription>{IMAGE_HINT}</FormDescription>
            </div>
          </div>
          <FormControl>
            <input
              ref={inputRef}
              type="file"
              accept={IMAGE_ACCEPT}
              className="sr-only"
              data-testid="product-image-input"
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = "" // allow re-picking the same file
                if (file) void upload.start(file)
              }}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  )
}
