interface StatCardProps {
  /** Ligature name from the Material Symbols font. */
  icon: string;
  label: string;
  subtitle?: string;
  value: number | string;
}

/** Dashboard tile: a caption, one big number and an optional hint line. */
export function StatCard(props: StatCardProps) {
  const { icon, label, subtitle, value } = props;
  return (
    <div className="rounded-xl border bg-card p-5 text-card-foreground shadow-lift">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-muted-foreground">{label}</p>
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-sahara-container text-white">
          <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
            {icon}
          </span>
        </span>
      </div>
      <p className="mt-2 font-heading text-3xl tabular-nums">{value}</p>
      {subtitle ? <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p> : null}
    </div>
  );
}
