import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { toast } from "sonner"

import { CartService } from "@/client"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { cartKeys } from "@/lib/queries/cart"
import { handleError } from "@/utils"

type AddVars = { productId: string; quantity?: number; name: string }

export function useAddToCart() {
  const { loggedIn } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const mutation = useMutation({
    mutationFn: async (vars: AddVars) =>
      (
        await CartService.addCartItem({
          body: { product_id: vars.productId, quantity: vars.quantity ?? 1 },
        })
      ).data,
    onSuccess: (cart, vars) => {
      queryClient.setQueryData(cartKeys.all, cart)
      toast.success("Added to cart", {
        description: vars.name,
        action: {
          label: "View cart",
          onClick: () => navigate({ to: "/cart" }),
        },
      })
    },
    onError: handleError.bind(showErrorToast),
  })

  const add = (vars: AddVars) => {
    if (!loggedIn) {
      const { pathname, search } = window.location
      navigate({ to: "/login", search: { redirect: pathname + search } })
      return
    }
    mutation.mutate(vars)
  }

  return {
    add,
    isPending: mutation.isPending,
    pendingId: mutation.variables?.productId,
  }
}
