import { createFileRoute } from "@tanstack/react-router"

import { AccountSettings } from "@/components/UserSettings/AccountSettings"
import { pageTitle } from "@/config"
import { requireUser } from "@/lib/auth"

export const Route = createFileRoute("/_store/account")({
  component: AccountSettings,
  beforeLoad: ({ location }) => requireUser(location),
  head: () => ({
    meta: [{ title: pageTitle("My account") }],
  }),
})
