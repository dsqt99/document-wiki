"use client";

import { Children, Fragment, isValidElement, useRef, useState, type ReactNode } from "react";
import { Combobox } from "@base-ui/react/combobox";
import { CheckIcon, ChevronDownIcon, SearchIcon } from "lucide-react";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/lib/i18n";
import { matchesOption } from "@/lib/select-search";
import { cn } from "@/lib/utils";

type Option = { value: string; label: string; disabled?: boolean; group?: string };
type Props = {
  value: string | number;
  onValueChange: (value: string) => void;
  children: ReactNode;
  id?: string;
  name?: string;
  title?: string;
  className?: string;
  disabled?: boolean;
  required?: boolean;
  searchable?: boolean;
  searchPlaceholder?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
};

function textOf(children: ReactNode): string {
  return Children.toArray(children).map((child) => isValidElement<{ children?: ReactNode }>(child) ? textOf(child.props.children) : String(child)).join("");
}

function optionsOf(children: ReactNode, group?: string, groupDisabled = false): Option[] {
  return Children.toArray(children).flatMap((child) => {
    if (!isValidElement<{ value?: string | number; children?: ReactNode; label?: string; disabled?: boolean }>(child)) return [];
    if (child.type === Fragment) return optionsOf(child.props.children, group, groupDisabled);
    if (child.type === "optgroup") return optionsOf(child.props.children, child.props.label, !!child.props.disabled);
    if (child.type !== "option") return [];
    const label = child.props.label ?? textOf(child.props.children);
    return [{ value: String(child.props.value ?? label), label, disabled: groupDisabled || child.props.disabled, group }];
  });
}

/** Styled replacement for option lists, with an optional search row inside the popup. */
export function OptionSelect({ value, onValueChange, children, searchable = false, searchPlaceholder, className, disabled, required, name, ...triggerProps }: Props) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const options = optionsOf(children);
  const selected = options.find((option) => option.value === String(value)) ?? null;
  const groups = [...new Set(options.map((option) => option.group))];

  if (!searchable) return (
    <Select items={options} value={String(value)} onValueChange={(next) => { if (next !== null) onValueChange(next); }} disabled={disabled} required={required} name={name}>
      <SelectTrigger {...triggerProps} className={cn("h-9 w-auto min-w-0", className)}><SelectValue /></SelectTrigger>
      <SelectContent align="start">
        {groups.map((group) => <SelectGroup key={group ?? "ungrouped"}>
          {group && <SelectLabel>{group}</SelectLabel>}
          {options.filter((option) => option.group === group).map((option) => <SelectItem key={option.value} value={option.value} disabled={option.disabled} title={option.label}>{option.label}</SelectItem>)}
        </SelectGroup>)}
      </SelectContent>
    </Select>
  );

  return (
    <Combobox.Root<Option> items={options} value={selected} inputValue={query} onInputValueChange={setQuery}
      onValueChange={(next) => { if (next) onValueChange(next.value); }}
      onOpenChange={() => setQuery("")} isItemEqualToValue={(a, b) => a.value === b.value}
      filter={(option, search) => !option.disabled && matchesOption(option.label, search)}
      autoHighlight disabled={disabled} required={required} name={name}>
      <Combobox.Trigger {...triggerProps} className={cn("flex h-9 w-full min-w-0 items-center justify-between gap-2 rounded-xl border border-input bg-background px-3 text-left text-sm shadow-xs transition-colors hover:bg-muted/40 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50", className)}>
        <span className="min-w-0 flex-1 truncate">{selected?.label ?? String(value)}</span><ChevronDownIcon className="size-4 shrink-0 text-muted-foreground" />
      </Combobox.Trigger>
      <Combobox.Portal>
        <Combobox.Positioner sideOffset={6} align="start" className="isolate z-50 outline-none">
          <Combobox.Popup initialFocus={input} className="flex max-h-(--available-height) w-[min(28rem,calc(100vw-2rem))] min-w-(--anchor-width) flex-col overflow-hidden rounded-xl border border-border bg-popover p-1.5 text-popover-foreground shadow-lg outline-none data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0">
            <div className="relative mb-1 border-b border-border pb-1.5">
              <SearchIcon className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
              <Combobox.Input ref={input} aria-label={searchPlaceholder ?? t("common.search")} placeholder={searchPlaceholder ?? t("common.search")} className="h-9 w-full rounded-lg bg-muted/50 pr-3 pl-9 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/30" />
            </div>
            <Combobox.Empty className="px-3 text-sm text-muted-foreground empty:hidden">{t("common.noResults")}</Combobox.Empty>
            <Combobox.List className="max-h-72 scroll-py-1 overflow-y-auto overscroll-contain">
              {(option: Option) => <Combobox.Item key={option.value} value={option} disabled={option.disabled} className="relative flex cursor-pointer items-center gap-2 rounded-lg py-2.5 pr-8 pl-3 text-sm outline-none select-none data-highlighted:bg-accent data-highlighted:text-accent-foreground data-disabled:pointer-events-none data-disabled:opacity-50">
                <span className="line-clamp-2 min-w-0 break-words" title={option.label}>{option.label}</span>
                <Combobox.ItemIndicator className="absolute right-2.5"><CheckIcon className="size-4" /></Combobox.ItemIndicator>
              </Combobox.Item>}
            </Combobox.List>
          </Combobox.Popup>
        </Combobox.Positioner>
      </Combobox.Portal>
    </Combobox.Root>
  );
}
