import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"

import { type ProductCreate, ProductsService } from "@/client"
import { ProductFormFields } from "@/components/Backoffice/Products/ProductFormFields"
import {
  type ProductFormValues,
  productSchema,
  toCreateBody,
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
  DialogTrigger,
} from "@/components/ui/dialog"
import { Form } from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useCategories } from "@/hooks/useCategories"
import useCustomToast from "@/hooks/useCustomToast"
import { useProductImageUpload } from "@/hooks/useProductImageUpload"
import { applyConflictError, applyImageError } from "@/lib/formErrors"
import { productKeys } from "@/lib/queries/products"
import { handleError } from "@/utils"

const emptyValues: ProductFormValues = {
  name: "",
  sku: "",
  category_uuid: "",
  price: "",
  stock: "0",
  weight: "",
  description: "",
  image_key: "",
}

const AddProduct = () => {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { categories } = useCategories()

  const form = useForm<ProductFormValues>({
    resolver: zodResolver(productSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: emptyValues,
  })

  const upload = useProductImageUpload((key) =>
    form.setValue("image_key", key, {
      shouldDirty: true,
      shouldValidate: true,
    }),
  )

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      upload.reset()
      form.reset(emptyValues)
    }
    setIsOpen(open)
  }

  const mutation = useMutation({
    mutationFn: (data: ProductCreate) =>
      ProductsService.createProduct({ body: data }),
    onSuccess: () => {
      showSuccessToast("Product created successfully")
      upload.reset()
      form.reset(emptyValues)
      setIsOpen(false)
    },
    onError: (err) => {
      const handled = applyConflictError(
        err,
        form,
        "sku",
        /sku/i,
        "A product with this SKU already exists",
      )
      if (!handled && !applyImageError(err, form))
        handleError.call(showErrorToast, err)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: productKeys.all })
    },
  })

  const onSubmit = (data: ProductFormValues) => {
    mutation.mutate(toCreateBody(data))
  }

  if (categories.length === 0) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <Button disabled>
                <Plus />
                Add Product
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>Create a category first</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button>
          <Plus />
          Add Product
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg max-h-[90svh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add Product</DialogTitle>
          <DialogDescription>
            Fill in the details to add a new product.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <div className="grid gap-4 py-4">
              <ProductFormFields
                form={form}
                upload={upload}
                currentImageUrl={null}
                savedImageKey=""
              />
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
              <LoadingButton
                type="submit"
                loading={mutation.isPending}
                disabled={upload.isUploading}
              >
                Save
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

export default AddProduct
