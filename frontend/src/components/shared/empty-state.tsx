import type { ReactNode } from "react";

type EmptyStateProps = {
  /** Material Symbols ligature name */
  icon: string;
  title: string;
  description?: string;
  action?: ReactNode;
};

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <span className="material-symbols-outlined mb-3 text-muted-foreground/40" style={{ fontSize: 48 }}>
        {icon}
      </span>
      <h3 className="text-lg font-medium">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
