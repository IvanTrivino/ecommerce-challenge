import { AxiosError } from "axios"

import type { OrderPublic } from "@/client"
import { extractErrorMessage } from "@/utils"

export type OrderState = OrderPublic["state"]

export const MAX_QUANTITY_PER_ITEM = 99 // backend MAX_QUANTITY_PER_ITEM
export const MY_ORDERS_PAGE_SIZE = 10

export type OrderTab =
  | "in_progress"
  | "completed"
  | "cancelled"
  | "placed"
  | "draft"

export const ORDER_TABS: {
  value: OrderTab
  label: string
  states: OrderState[]
}[] = [
  { value: "in_progress", label: "In progress", states: ["in_progress"] },
  { value: "completed", label: "Completed", states: ["completed"] },
  { value: "cancelled", label: "Cancelled", states: ["cancelled"] },
  {
    value: "placed",
    label: "All placed",
    states: ["in_progress", "completed", "cancelled"],
  },
  { value: "draft", label: "Drafts", states: ["draft"] },
]

export const canAct = (order: { state: OrderState }) =>
  order.state === "in_progress"

// The status code and detail of an API error, for flows that branch on them
export function apiError(err: unknown): { status?: number; detail: string } {
  return {
    status: err instanceof AxiosError ? err.response?.status : undefined,
    detail: extractErrorMessage(err as Error),
  }
}
