import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query"

import { handleApiError } from "@/lib/apiErrors"

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
})
