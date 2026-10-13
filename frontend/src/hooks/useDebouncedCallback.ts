import { useCallback, useEffect, useRef } from "react"

export function useDebouncedCallback<A extends unknown[]>(
  callback: (...args: A) => void,
  delay: number,
) {
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const latest = useRef(callback)
  latest.current = callback

  useEffect(() => () => clearTimeout(timer.current), [])

  return useCallback(
    (...args: A) => {
      clearTimeout(timer.current)
      timer.current = setTimeout(() => latest.current(...args), delay)
    },
    [delay],
  )
}
