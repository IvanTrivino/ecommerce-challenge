import { EllipsisVertical } from "lucide-react"
import { useState } from "react"

import type { ProductCategoryPublic } from "@/client"
import DeleteCategory from "@/components/Backoffice/Categories/DeleteCategory"
import EditCategory from "@/components/Backoffice/Categories/EditCategory"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

interface CategoryActionsMenuProps {
  category: ProductCategoryPublic
}

export const CategoryActionsMenu = ({ category }: CategoryActionsMenuProps) => {
  const [open, setOpen] = useState(false)

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon">
          <EllipsisVertical />
          <span className="sr-only">Category actions</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <EditCategory category={category} onSuccess={() => setOpen(false)} />
        <DeleteCategory id={category.id} onSuccess={() => setOpen(false)} />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
