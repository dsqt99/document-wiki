import { cn } from "@/lib/utils";
import { hexAlpha } from "./types";

/** Rounded pill tinted with a knowledge type's colour (text = colour, border ~33%, fill ~7%). */
export function TypePill({
  name,
  color,
  className,
}: {
  name: string;
  color?: string | null;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center truncate rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
        !color && "border-border text-muted-foreground",
        className
      )}
      style={
        color
          ? { color, borderColor: hexAlpha(color, 0.33), backgroundColor: hexAlpha(color, 0.07) }
          : undefined
      }
    >
      {name}
    </span>
  );
}
