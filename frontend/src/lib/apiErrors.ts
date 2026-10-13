import { AxiosError } from "axios"

import { clearSession } from "@/lib/auth"
import { getRouter } from "@/lib/routerRef"

const isProtected = (path: string) =>
  path.startsWith("/admin") ||
  path === "/account" ||
  path === "/cart" ||
  path === "/checkout" ||
  path.startsWith("/orders")

function isSessionInvalid(err: AxiosError) {
  const status = err.response?.status
  const detail = (err.response?.data as { detail?: unknown } | undefined)
    ?.detail
  const isMe = err.config?.url?.endsWith("/users/me")
  return (
    status === 401 ||
    (status === 403 && detail === "Could not validate credentials") ||
    (!!isMe && (status === 404 || status === 400))
  )
}

export function handleApiError(error: Error) {
  if (!(error instanceof AxiosError) || !isSessionInvalid(error)) return
  clearSession()
  const { pathname, search } = window.location
  if (isProtected(pathname)) {
    getRouter()?.navigate({
      to: "/login",
      search: { redirect: pathname + search },
    })
  }
}
