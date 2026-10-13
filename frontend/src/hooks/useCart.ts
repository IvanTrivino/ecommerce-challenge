import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { type CartPublic, CartService } from "@/client"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { cartKeys, cartQueryOptions } from "@/lib/queries/cart"
import { extractErrorMessage } from "@/utils"

export function useCart() {
  const { loggedIn } = useAuth()
  return useQuery({ ...cartQueryOptions, enabled: loggedIn })
}

export function useCartMutations() {
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()
  const setCart = (cart: CartPublic) =>
    queryClient.setQueryData(cartKeys.all, cart)
  const onError = (err: Error) => {
    showErrorToast(extractErrorMessage(err))
    // The server may know better (stock changed, line gone): resync
    queryClient.invalidateQueries({ queryKey: cartKeys.all })
  }

  const update = useMutation({
    mutationFn: async ({ id, quantity }: { id: string; quantity: number }) =>
      (
        await CartService.updateCartItem({
          path: { item_id: id },
          body: { quantity },
        })
      ).data,
    onSuccess: setCart,
    onError,
  })

  const remove = useMutation({
    mutationFn: async (id: string) =>
      (await CartService.removeCartItem({ path: { item_id: id } })).data,
    onSuccess: setCart,
    onError,
  })

  return { update, remove }
}
