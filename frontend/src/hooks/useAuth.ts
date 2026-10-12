import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useSyncExternalStore } from "react"

import {
  type Body_login_login_access_token as AccessToken,
  LoginService,
  type UserRegister,
  UsersService,
} from "@/client"
import {
  clearSession,
  homeFor,
  isLoggedIn,
  isSafeRedirect,
  setToken,
  subscribeAuth,
} from "@/lib/auth"
import { currentUserQueryOptions } from "@/lib/queries/users"
import { handleError } from "@/utils"
import useCustomToast from "./useCustomToast"

const useAuth = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const loggedIn = useSyncExternalStore(subscribeAuth, isLoggedIn)
  const { data } = useQuery({
    ...currentUserQueryOptions,
    enabled: loggedIn,
  })
  const user = loggedIn ? data : undefined

  const signUpMutation = useMutation({
    mutationFn: (data: UserRegister) =>
      UsersService.registerUser({ body: data }),
    onSuccess: () => {
      navigate({ to: "/login" })
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const login = async ({
    redirect,
    ...credentials
  }: AccessToken & { redirect?: string }) => {
    const response = await LoginService.loginAccessToken({
      body: credentials,
    })
    setToken(response.data.access_token)
    const currentUser = await queryClient.fetchQuery(currentUserQueryOptions)
    return { currentUser, redirect }
  }

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: ({ currentUser, redirect }) => {
      if (isSafeRedirect(redirect)) {
        navigate({ to: redirect })
      } else {
        navigate({ to: homeFor(currentUser) })
      }
    },
    onError: handleError.bind(showErrorToast),
  })

  const logout = () => {
    clearSession()
    navigate({ to: "/" })
  }

  return {
    signUpMutation,
    loginMutation,
    logout,
    user,
    loggedIn,
  }
}

export default useAuth
