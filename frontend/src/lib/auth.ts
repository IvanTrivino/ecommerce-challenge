import { type ParsedLocation, redirect } from "@tanstack/react-router"

import type { UserPublic } from "@/client"
import { currentUserQueryOptions } from "@/lib/queries/users"
import { queryClient } from "@/lib/queryClient"

export const isLoggedIn = () => localStorage.getItem("access_token") !== null

// Lets components re-render when the token changes outside React
const listeners = new Set<() => void>()
const notifyAuthChange = () => {
  for (const listener of listeners) listener()
}

export function subscribeAuth(listener: () => void) {
  listeners.add(listener)
  window.addEventListener("storage", listener)
  return () => {
    listeners.delete(listener)
    window.removeEventListener("storage", listener)
  }
}

export function setToken(token: string) {
  localStorage.setItem("access_token", token)
  notifyAuthChange()
}

export function clearSession() {
  localStorage.removeItem("access_token")
  queryClient.removeQueries({ queryKey: currentUserQueryOptions.queryKey })
  notifyAuthChange()
}

export const isSafeRedirect = (to?: string): to is string =>
  !!to && to.startsWith("/") && !to.startsWith("//")

export const homeFor = (user: UserPublic | null | undefined) =>
  user?.is_superuser ? "/admin" : "/"

export async function requireUser(location: ParsedLocation) {
  if (!isLoggedIn()) {
    throw redirect({ to: "/login", search: { redirect: location.href } })
  }
  return queryClient.ensureQueryData(currentUserQueryOptions)
}

export async function requireSuperuser(location: ParsedLocation) {
  const user = await requireUser(location)
  if (!user.is_superuser) throw redirect({ to: "/" })
  return user
}

export async function redirectIfLoggedIn() {
  if (!isLoggedIn()) return
  const user = await queryClient
    .ensureQueryData(currentUserQueryOptions)
    .catch(() => null)
  if (user) throw redirect({ to: homeFor(user) })
}
