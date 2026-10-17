"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** One-at-a-time floating notice; a newer message replaces the current one. */
export function useToast(durationMs: number) {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = useCallback(
    (msg: string) => {
      if (timer.current) clearTimeout(timer.current);
      setMessage(msg);
      timer.current = setTimeout(() => setMessage(null), durationMs);
    },
    [durationMs],
  );

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  return { message, show };
}

export function Toast({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed right-6 bottom-6 z-[60] max-w-sm rounded-lg bg-foreground px-4 py-2.5 text-sm text-background shadow-lg animate-in fade-in-0 slide-in-from-bottom-2"
    >
      {message}
    </div>
  );
}
