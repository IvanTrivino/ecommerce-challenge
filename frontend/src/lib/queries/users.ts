import { queryOptions } from "@tanstack/react-query"

import { UsersService } from "@/client"

export const currentUserQueryOptions = queryOptions({
  queryKey: ["currentUser"],
  queryFn: async () => (await UsersService.readUserMe()).data,
})

export const usersQueryOptions = queryOptions({
  queryKey: ["users"],
  queryFn: async () =>
    (await UsersService.readUsers({ query: { skip: 0, limit: 100 } })).data,
})

export const usersCountQueryOptions = queryOptions({
  queryKey: ["users", "count"],
  queryFn: async () =>
    (await UsersService.readUsers({ query: { limit: 1 } })).data.count,
})
