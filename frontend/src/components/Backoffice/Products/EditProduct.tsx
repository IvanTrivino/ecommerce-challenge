import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Pencil } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"

import {
  type ProductPublic,
  ProductsService,
  type ProductUpdate,
} from "@/client"
import { ProductFormFields } from "@/components/Backoffice/Products/ProductFormFields"
import {
  type ProductFormValues,
  productSchema,
  toUpdateBody,
} from "@/components/Backoffice/Products/productSchema"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import { Form } from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { applyConflictError } from "@/lib/formErrors"
import { productKeys } from "@/lib/queries/products"
import { handleError } from "@/utils"

interface EditProductProps {
  product: ProductPublic
  onSuccess: () => void
}

const EditProduct = ({ product, onSuccess }: EditProductProps) => {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const form = useForm<ProductFormValues>({
    resolver: zodResolver(productSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      name: product.name,
      sku: product.sku,
      category_uuid: product.category_uuid,
      price: product.price,
      stock: String(product.stock ?? 0),
      weight: product.weight ?? "",
      description: product.description ?? "",
    },
  })

  // read during render so react-hook-form tracks it
  const { dirtyFields } = form.formState

  const mutation = useMutation({
    mutationFn: (data: ProductUpdate) =>
      ProductsService.updateProduct({
        path: { product_id: product.id },
        body: data,
      }),
    onSuccess: () => {
      showSuccessToast("Product updated successfully")
      form.reset(form.getValues())
      setIsOpen(false)
      onSuccess()
    },
    onError: (err) => {
      const handled = applyConflictError(
        err,
        form,
        "sku",
        /sku/i,
        "A product with this SKU already exists",
      )
      if (!handled) handleError.call(showErrorToast, err)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: productKeys.all })
    },
  })

  const onSubmit = (data: ProductFormValues) => {
    const changes = toUpdateBody(data, dirtyFields)
    if (Object.keys(changes).length === 0) {
      setIsOpen(false)
      return
    }
    mutation.mutate(changes)
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuItem
        onSelect={(e) => e.preventDefault()}
        onClick={() => setIsOpen(true)}
      >
        <Pencil />
        Edit Product
      </DropdownMenuItem>
      <DialogContent className="sm:max-w-lg max-h-[90svh] overflow-y-auto">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <DialogHeader>
              <DialogTitle>Edit Product</DialogTitle>
              <DialogDescription>
                Update the product details below.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <ProductFormFields form={form} />
            </div>

            <DialogFooter>
              <DialogClose asChild>
                <Button
                  type="button"
                  variant="outline"
                  disabled={mutation.isPending}
                >
                  Cancel
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={mutation.isPending}>
                Save
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

export default EditProduct
