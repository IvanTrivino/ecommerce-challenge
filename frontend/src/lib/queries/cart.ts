import { queryOptions } from "@tanstack/react-query"

import { CartService } from "@/client"

export const cartKeys = { all: ["cart"] as const }

// Components add `enabled: loggedIn`: the cart endpoints answer 401 to visitors
export const cartQueryOptions = queryOptions({
  queryKey: cartKeys.all,
  queryFn: async () => (await CartService.readCart()).data,
  staleTime: 30_000,
})
