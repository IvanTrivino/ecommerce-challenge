import { Minus, Plus } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useDebouncedCallback } from "@/hooks/useDebouncedCallback"

const DEBOUNCE_MS = 400

type Props = {
  value: number
  max: number
  label: string
  onChange: (quantity: number) => void
}

export function QuantityStepper({ value, max, label, onChange }: Props) {
  const [text, setText] = useState(String(value))
  const current = useRef(value)
  current.current = value

  // The server's answer is the source of truth
  useEffect(() => setText(String(value)), [value])

  const send = useDebouncedCallback((quantity: number) => {
    if (quantity !== current.current) onChange(quantity)
  }, DEBOUNCE_MS)

  const apply = (raw: number) => {
    if (Number.isNaN(raw)) return
    const quantity = Math.min(max, Math.max(1, Math.trunc(raw)))
    setText(String(quantity))
    send(quantity)
  }

  const shown = Number(text) || value

  return (
    <div className="flex items-center gap-1">
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="size-8"
        aria-label={`Decrease quantity of ${label}`}
        disabled={shown <= 1}
        onClick={() => apply(shown - 1)}
      >
        <Minus aria-hidden />
      </Button>
      <Input
        type="number"
        inputMode="numeric"
        min={1}
        max={max}
        value={text}
        className="h-8 w-14 px-2 text-center"
        aria-label={`Quantity for ${label}`}
        data-testid="quantity-input"
        onChange={(e) => {
          setText(e.target.value)
          if (e.target.value !== "") apply(Number(e.target.value))
        }}
        onBlur={() => setText(String(shown))}
      />
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="size-8"
        aria-label={`Increase quantity of ${label}`}
        disabled={shown >= max}
        onClick={() => apply(shown + 1)}
      >
        <Plus aria-hidden />
      </Button>
    </div>
  )
}
