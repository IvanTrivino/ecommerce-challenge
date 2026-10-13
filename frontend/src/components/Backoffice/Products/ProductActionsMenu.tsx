import { EllipsisVertical, Pencil, Trash2 } from "lucide-react"
import { useState } from "react"

import type { ProductPublic } from "@/client"
import DeleteProduct from "@/components/Backoffice/Products/DeleteProduct"
import EditProduct from "@/components/Backoffice/Products/EditProduct"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export const ProductActionsMenu = ({ product }: { product: ProductPublic }) => {
  // The dialogs live outside the menu: the menu closes when the window loses
  // focus (e.g. the file picker opens) and would unmount them with it
  const [dialog, setDialog] = useState<"edit" | "delete" | null>(null)
  const close = () => setDialog(null)

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon">
            <EllipsisVertical />
            <span className="sr-only">Product actions</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setDialog("edit")}>
            <Pencil />
            Edit Product
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onSelect={() => setDialog("delete")}
          >
            <Trash2 />
            Delete Product
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {dialog === "edit" && <EditProduct product={product} onClose={close} />}
      {dialog === "delete" && <DeleteProduct id={product.id} onClose={close} />}
    </>
  )
}
