import { cn } from "@/lib/utils"

interface ProgressBarProps {
  value: number
  label: string
  className?: string
}

export function ProgressBar({ value, label, className }: ProgressBarProps) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
      className={cn("h-1.5 w-full rounded bg-muted", className)}
    >
      <div
        className="h-full rounded bg-primary transition-[width]"
        style={{ width: `${value}%` }}
      />
    </div>
  )
}
