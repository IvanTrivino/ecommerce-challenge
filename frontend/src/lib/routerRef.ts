import type { AnyRouter } from "@tanstack/react-router"

// Lets non-React modules navigate without importing the route tree (circular)
let current: AnyRouter | undefined

export const setRouter = (router: AnyRouter) => {
  current = router
}

export const getRouter = () => current
