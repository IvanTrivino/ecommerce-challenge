import { keepPreviousData, queryOptions } from "@tanstack/react-query"

import { OrdersService, UsersService } from "@/client"
import type { OrderState } from "@/lib/orders"

export const orderKeys = {
  all: ["orders"] as const,
  mine: (page: number) => ["orders", "mine", page] as const,
  myDetail: (id: string) => ["orders", "mine", "detail", id] as const,
  admin: (states: OrderState[], page: number) =>
    ["orders", "admin", states, page] as const,
  adminDetail: (id: string) => ["orders", "admin", "detail", id] as const,
}

export const myOrdersQueryOptions = (page: number, pageSize: number) =>
  queryOptions({
    queryKey: orderKeys.mine(page),
    queryFn: async () =>
      (
        await UsersService.readMyOrders({
          query: { skip: (page - 1) * pageSize, limit: pageSize },
        })
      ).data,
    placeholderData: keepPreviousData,
  })

export const myOrderQueryOptions = (id: string) =>
  queryOptions({
    queryKey: orderKeys.myDetail(id),
    queryFn: async () =>
      (await UsersService.readMyOrder({ path: { order_id: id } })).data,
  })

export const adminOrdersQueryOptions = ({
  states,
  page,
  pageSize,
}: {
  states: OrderState[]
  page: number
  pageSize: number
}) =>
  queryOptions({
    queryKey: orderKeys.admin(states, page),
    queryFn: async () =>
      (
        await OrdersService.readOrders({
          query: {
            state: states,
            skip: (page - 1) * pageSize,
            limit: pageSize,
          },
        })
      ).data,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: true,
  })

export const adminOrderQueryOptions = (id: string) =>
  queryOptions({
    queryKey: orderKeys.adminDetail(id),
    queryFn: async () =>
      (await OrdersService.readOrder({ path: { order_id: id } })).data,
  })
