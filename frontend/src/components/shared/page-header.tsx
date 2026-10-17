import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  description?: string;
  action?: ReactNode;
};

/**
 * Page title block. The three data-slot attributes are a contract with the embed CSS
 * in globals.css, which hides the text part when the wiki runs inside the chatbot.
 */
export function PageHeader({ title, description, action }: PageHeaderProps) {
  return (
    <div data-slot="page-header" className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div data-slot="page-header-text" className="min-w-0">
        <h2 className="text-3xl font-normal tracking-tight lg:text-4xl">{title}</h2>
        {description && <p className="mt-1.5 max-w-xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {action && (
        <div data-slot="page-header-action" className="flex shrink-0 flex-wrap items-center gap-2 sm:ml-auto">
          {action}
        </div>
      )}
    </div>
  );
}
