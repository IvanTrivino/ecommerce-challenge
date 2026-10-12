import { createFileRoute } from "@tanstack/react-router"

import { pageTitle } from "@/config"

export const Route = createFileRoute("/admin/products")({
  component: () => <h1 className="text-2xl font-bold">Products</h1>,
  head: () => ({
    meta: [{ title: pageTitle("Products") }],
  }),
})
