import type { ProductImportPublic } from "@/client"
import { Badge } from "@/components/ui/badge"

type BadgeVariant = "default" | "secondary" | "destructive" | "outline"

function describe(i: ProductImportPublic): {
  variant: BadgeVariant
  text: string
} {
  switch (i.status) {
    case "pending":
      return { variant: "secondary", text: "Queued" }
    case "running":
      return { variant: "default", text: "Running" }
    case "completed":
      return {
        variant: "outline",
        text: i.error_count > 0 ? "Completed with errors" : "Completed",
      }
    case "failed":
      return { variant: "destructive", text: "Failed" }
  }
}

export function ImportStatusBadge({
  productImport,
}: {
  productImport: ProductImportPublic
}) {
  const { variant, text } = describe(productImport)
  return (
    <Badge variant={variant} data-testid="import-status">
      {text}
    </Badge>
  )
}
