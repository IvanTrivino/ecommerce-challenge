import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Pencil } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"

import {
  ProductCategoriesService,
  type ProductCategoryPublic,
  type ProductCategoryUpdate,
} from "@/client"
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
} from "@/components/ui/dialog"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import { Form } from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { applyConflictError } from "@/lib/formErrors"
import { categoryKeys } from "@/lib/queries/categories"
import { productKeys } from "@/lib/queries/products"
import { handleError } from "@/utils"

interface EditCategoryProps {
  category: ProductCategoryPublic
  onSuccess: () => void
}

const EditCategory = ({ category, onSuccess }: EditCategoryProps) => {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const form = useForm<CategoryFormValues>({
    resolver: zodResolver(categorySchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: { name: category.name, code: category.code },
  })

  // read during render so react-hook-form tracks it
  const { dirtyFields } = form.formState

  const mutation = useMutation({
    mutationFn: (data: ProductCategoryUpdate) =>
      ProductCategoriesService.updateCategory({
        path: { category_id: category.id },
        body: data,
      }),
    onSuccess: () => {
      showSuccessToast("Category updated successfully")
      form.reset(form.getValues())
      setIsOpen(false)
      onSuccess()
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
    const { name, code } = dirtyFields
    const changes: ProductCategoryUpdate = {}
    if (name) changes.name = data.name
    if (code) changes.code = data.code
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
        Edit Category
      </DropdownMenuItem>
      <DialogContent className="sm:max-w-md">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <DialogHeader>
              <DialogTitle>Edit Category</DialogTitle>
              <DialogDescription>
                Update the category details below.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <CategoryFormFields form={form} />
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

export default EditCategory
