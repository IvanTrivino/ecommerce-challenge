import { LayoutDashboard, Package, Store, Tags, Users } from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"

const adminItems: Item[] = [
  { icon: LayoutDashboard, title: "Overview", path: "/admin" },
  { icon: Package, title: "Products", path: "/admin/products" },
  { icon: Tags, title: "Categories", path: "/admin/categories" },
  { icon: Users, title: "Users", path: "/admin/users" },
]

const storeItems: Item[] = [{ icon: Store, title: "View store", path: "/" }]

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" to="/admin" />
      </SidebarHeader>
      <SidebarContent>
        <Main items={adminItems} />
        <Main items={storeItems} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
