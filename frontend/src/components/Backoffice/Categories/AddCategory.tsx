import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"

import { ProductCategoriesService, type ProductCategoryCreate } from "@/client"
import { CategoryFormFields } from "@/components/Backoffice/Categories/CategoryFormFields"
import {
  type CategoryFormValues,
  categorySchema,
} from "@/components/Backoffice/Categories/categorySchema"
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
import useCustomToast from "@/hooks/useCustomToast"
import { applyConflictError } from "@/lib/formErrors"
import { categoryKeys } from "@/lib/queries/categories"
import { productKeys } from "@/lib/queries/products"
import { handleError } from "@/utils"

const AddCategory = () => {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const form = useForm<CategoryFormValues>({
    resolver: zodResolver(categorySchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: { name: "", code: "" },
  })

  const mutation = useMutation({
    mutationFn: (data: ProductCategoryCreate) =>
      ProductCategoriesService.createCategory({ body: data }),
    onSuccess: () => {
      showSuccessToast("Category created successfully")
      form.reset()
      setIsOpen(false)
    },
    onError: (err) => {
      if (!applyConflictError(err, form, "code", /code/i)) {
        handleError.call(showErrorToast, err)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: categoryKeys.all })
      queryClient.invalidateQueries({ queryKey: productKeys.all })
    },
  })

  const onSubmit = (data: CategoryFormValues) => {
    mutation.mutate(data)
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button className="my-4">
          <Plus className="mr-2" />
          Add Category
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Category</DialogTitle>
          <DialogDescription>
            Fill in the details to add a new category.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <div className="grid gap-4 py-4">
              <CategoryFormFields form={form} autoSlug />
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

export default AddCategory
