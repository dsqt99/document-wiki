"use client";

type Shortcut = { keys: string; action: string };

/** Review desk key bindings, in the order they are shown. */
const REVIEW_SHORTCUTS: readonly Shortcut[] = [
  { keys: "j / ↓", action: "Next draft" },
  { keys: "k / ↑", action: "Previous draft" },
  { keys: "a", action: "Approve current draft" },
  { keys: "c", action: "Request changes (focus note)" },
  { keys: "r", action: "Reject (focus note)" },
  { keys: "Esc", action: "Cancel pending action" },
  { keys: "?", action: "Toggle this help" },
];

/** Full-screen overlay listing the review desk keyboard shortcuts. Clicking outside closes it. */
export function ShortcutHelp({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-shortcuts-title"
        className="w-full max-w-md rounded-2xl border bg-popover p-5 text-popover-foreground shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 id="review-shortcuts-title" className="text-base font-semibold">
            Keyboard shortcuts
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              close
            </span>
          </button>
        </div>
        <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 text-sm">
          {REVIEW_SHORTCUTS.map((shortcut) => (
            <div key={shortcut.keys} className="contents">
              <dt>
                <kbd className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{shortcut.keys}</kbd>
              </dt>
              <dd>{shortcut.action}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-xs text-muted-foreground italic">Shortcuts disabled while focus is in a text field.</p>
      </div>
    </div>
  );
}
