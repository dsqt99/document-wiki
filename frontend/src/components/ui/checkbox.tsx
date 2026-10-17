"use client"

import * as React from "react"
import { CheckIcon } from "lucide-react"

import { cn } from "@/lib/utils"

export type CheckboxProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "type"> & {
  onCheckedChange?: (checked: boolean) => void
}

/**
 * Native checkbox with a custom-drawn 16px box. The real <input> stays in the DOM
 * (visually covering the box) so forms, labels and keyboard focus behave natively.
 */
const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { className, onCheckedChange, disabled, ...props },
  ref
) {
  return (
    <span
      data-slot="checkbox"
      className={cn(
        "relative inline-flex size-4 shrink-0 items-center justify-center align-middle",
        disabled && "cursor-not-allowed opacity-50",
        className
      )}
    >
      <input
        ref={ref}
        type="checkbox"
        disabled={disabled}
        className="peer absolute inset-0 m-0 size-full cursor-pointer appearance-none rounded-[4px] border border-primary bg-background transition-colors outline-none checked:bg-primary focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed"
        onChange={(event) => onCheckedChange?.(event.target.checked)}
        {...props}
      />
      <CheckIcon
        aria-hidden
        className="pointer-events-none relative size-3 text-white opacity-0 peer-checked:opacity-100"
        strokeWidth={3}
      />
    </span>
  )
})

export { Checkbox }
