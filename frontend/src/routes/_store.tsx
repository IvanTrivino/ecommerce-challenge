import { createFileRoute, Outlet } from "@tanstack/react-router"

import { Footer } from "@/components/Common/Footer"
import { StoreHeader } from "@/components/Store/StoreHeader"
import { categoriesQueryOptions } from "@/lib/queries/categories"

export const Route = createFileRoute("/_store")({
  component: StoreLayout,
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(categoriesQueryOptions),
})

function StoreLayout() {
  return (
    <div className="flex min-h-svh flex-col">
      <StoreHeader />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:py-8">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}
