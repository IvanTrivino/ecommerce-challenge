import { createFileRoute } from "@tanstack/react-router"

import { pageTitle } from "@/config"

export const Route = createFileRoute("/admin/categories")({
  component: () => <h1 className="text-2xl font-bold">Categories</h1>,
  head: () => ({
    meta: [{ title: pageTitle("Categories") }],
  }),
})
