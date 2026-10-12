import { EllipsisVertical } from "lucide-react"
import { useState } from "react"

import type { ProductPublic } from "@/client"
import DeleteProduct from "@/components/Backoffice/Products/DeleteProduct"
import EditProduct from "@/components/Backoffice/Products/EditProduct"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export const ProductActionsMenu = ({ product }: { product: ProductPublic }) => {
  const [open, setOpen] = useState(false)

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon">
          <EllipsisVertical />
          <span className="sr-only">Product actions</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <EditProduct product={product} onSuccess={() => setOpen(false)} />
        <DeleteProduct id={product.id} onSuccess={() => setOpen(false)} />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
