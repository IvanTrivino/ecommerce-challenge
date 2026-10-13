import { EllipsisVertical, Pencil, Trash2 } from "lucide-react"
import { useState } from "react"

import type { ProductCategoryPublic } from "@/client"
import DeleteCategory from "@/components/Backoffice/Categories/DeleteCategory"
import EditCategory from "@/components/Backoffice/Categories/EditCategory"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

interface CategoryActionsMenuProps {
  category: ProductCategoryPublic
}

export const CategoryActionsMenu = ({ category }: CategoryActionsMenuProps) => {
  // The dialogs live outside the menu: the menu closes when the window loses
  // focus and would unmount them with it
  const [dialog, setDialog] = useState<"edit" | "delete" | null>(null)
  const close = () => setDialog(null)

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon">
            <EllipsisVertical />
            <span className="sr-only">Category actions</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setDialog("edit")}>
            <Pencil />
            Edit Category
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onSelect={() => setDialog("delete")}
          >
            <Trash2 />
            Delete Category
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {dialog === "edit" && (
        <EditCategory category={category} onClose={close} />
      )}
      {dialog === "delete" && (
        <DeleteCategory id={category.id} onClose={close} />
      )}
    </>
  )
}
