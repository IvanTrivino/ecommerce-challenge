import { createFileRoute } from "@tanstack/react-router"

import { AccountSettings } from "@/components/UserSettings/AccountSettings"
import { pageTitle } from "@/config"

export const Route = createFileRoute("/admin/settings")({
  component: AccountSettings,
  head: () => ({
    meta: [{ title: pageTitle("Settings") }],
  }),
})
