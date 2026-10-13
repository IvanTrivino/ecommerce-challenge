import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useRef, useState } from "react"
import { toast } from "sonner"

import { type OrderSummaryPublic, OrdersService } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import useCustomToast from "@/hooks/useCustomToast"
import { canAct } from "@/lib/orders"
import { orderKeys } from "@/lib/queries/orders"
import { productKeys } from "@/lib/queries/products"
import { handleError } from "@/utils"

type Props = {
  order: OrderSummaryPublic
  kind: "cancel" | "complete"
  size?: "sm" | "default"
}

const CONFIG = {
  cancel: {
    label: "Cancel",
    verb: "cancelled",
    title: (n: string) => `Cancel order #${n}?`,
    description: (count: number) =>
      `Its ${count} items go back into stock and the customer is emailed.`,
    confirm: "Cancel order",
    close: "Keep order",
    toast: (n: string) => `Order #${n} cancelled`,
    run: (id: string) => OrdersService.cancelOrder({ path: { order_id: id } }),
  },
  complete: {
    label: "Complete",
    verb: "completed",
    title: (n: string) => `Mark order #${n} as completed?`,
    description: () => "The customer is emailed.",
    confirm: "Mark completed",
    close: "Close",
    toast: (n: string) => `Order #${n} completed`,
    run: (id: string) =>
      OrdersService.completeOrder({ path: { order_id: id } }),
  },
} as const

export function OrderActionButton({ order, kind, size = "default" }: Props) {
  const config = CONFIG[kind]
  const [open, setOpen] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()
  const enabled = canAct(order)

  const mutation = useMutation({
    mutationFn: async () => (await config.run(order.id)).data,
    onSuccess: () => {
      toast.success(config.toast(order.number))
      setOpen(false)
    },
    // A 409 means someone else acted first: close the dialog so the refetched
    // row shows the real state
    onError: (err: Error) => {
      setOpen(false)
      handleError.call(showErrorToast, err)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: orderKeys.all })
      if (kind === "cancel") {
        queryClient.invalidateQueries({ queryKey: productKeys.all })
      }
    },
  })

  const button = (
    <Button
      ref={buttonRef}
      type="button"
      size={size}
      variant={kind === "cancel" ? "outline" : "default"}
      className={
        kind === "cancel"
          ? "text-destructive hover:text-destructive"
          : undefined
      }
      disabled={!enabled}
      aria-label={`${config.label} order ${order.number}`}
      data-testid={`${kind}-order`}
      onClick={() => setOpen(true)}
    >
      {config.label}
    </Button>
  )

  return (
    <>
      {enabled ? (
        button
      ) : (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex">{button}</span>
          </TooltipTrigger>
          <TooltipContent>
            Only in-progress orders can be {config.verb}
          </TooltipContent>
        </Tooltip>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="sm:max-w-md"
          onCloseAutoFocus={(event) => {
            // There is no DialogTrigger, so give focus back to the button by hand
            event.preventDefault()
            buttonRef.current?.focus()
          }}
        >
          <DialogHeader>
            <DialogTitle>{config.title(order.number)}</DialogTitle>
            <DialogDescription>
              {config.description(order.item_count)}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4">
            <DialogClose asChild>
              <Button
                type="button"
                variant="outline"
                disabled={mutation.isPending}
              >
                {config.close}
              </Button>
            </DialogClose>
            <LoadingButton
              type="button"
              variant={kind === "cancel" ? "destructive" : "default"}
              loading={mutation.isPending}
              onClick={() => mutation.mutate()}
              data-testid="confirm-order-action"
            >
              {config.confirm}
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
