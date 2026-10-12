import { z } from "zod"

export const categorySchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(255),
  code: z.string().trim().min(1, "Code is required").max(50),
})

export type CategoryFormValues = z.infer<typeof categorySchema>
