import { useEffect } from "react"
import type { UseFormReturn } from "react-hook-form"

import type { CategoryFormValues } from "@/components/Backoffice/Categories/categorySchema"
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { slugify } from "@/lib/utils"

interface CategoryFormFieldsProps {
  form: UseFormReturn<CategoryFormValues>
  // fills Code from Name until the user edits Code by hand
  autoSlug?: boolean
}

export function CategoryFormFields({
  form,
  autoSlug = false,
}: CategoryFormFieldsProps) {
  const name = form.watch("name")
  const codeEdited = !!form.formState.dirtyFields.code

  useEffect(() => {
    if (autoSlug && !codeEdited) {
      form.setValue("code", slugify(name))
    }
  }, [autoSlug, codeEdited, name, form])

  return (
    <>
      <FormField
        control={form.control}
        name="name"
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              Name <span className="text-destructive">*</span>
            </FormLabel>
            <FormControl>
              <Input placeholder="Name" type="text" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="code"
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              Code <span className="text-destructive">*</span>
            </FormLabel>
            <FormControl>
              <Input placeholder="Code" type="text" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  )
}
