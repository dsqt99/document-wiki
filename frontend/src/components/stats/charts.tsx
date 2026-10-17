"use client";

/**
 * Lightweight SVG charts for the statistics dashboard. No charting library: the
 * dashboard only needs a sparkline-style trend line and a horizontal bar list.
 */

export const CHART_COLORS = {
  blue: "#3b82f6",
  earth: "#c2703d",
  wine: "#b4413c",
  lilac: "#a78bfa",
  green: "#16a34a",
} as const;

export type LinePoint = { date: string; value: number | null };

type LineChartProps = {
  data: LinePoint[];
  height?: number;
  color?: string;
  label?: string;
};

const VIEW_WIDTH = 600;
const PAD = { left: 28, right: 8, top: 8, bottom: 18 };

export function LineChart({ data, height = 120, color = CHART_COLORS.blue, label }: LineChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex h-[120px] items-center justify-center text-xs text-muted-foreground/60">No data</div>
    );
  }

  const values = data.map((d) => (typeof d.value === "number" && Number.isFinite(d.value) ? d.value : 0));
  const max = Math.max(1, ...values);
  const min = Math.min(0, ...values);
  const span = max - min || 1;

  const plotW = VIEW_WIDTH - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const baseY = PAD.top + plotH;

  const xAt = (i: number) => (data.length === 1 ? PAD.left + plotW / 2 : PAD.left + (i / (data.length - 1)) * plotW);
  const yAt = (v: number) => PAD.top + (1 - (v - min) / span) * plotH;

  const points = values.map((v, i) => ({ x: xAt(i), y: yAt(v), v, date: data[i].date }));
  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
  const areaPath =
    `${linePath} L${points[points.length - 1].x.toFixed(2)},${baseY.toFixed(2)}` +
    ` L${points[0].x.toFixed(2)},${baseY.toFixed(2)} Z`;

  const gridYs = [0.25, 0.5, 0.75].map((f) => PAD.top + f * plotH);
  const first = data[0].date;
  const last = data[data.length - 1].date;

  return (
    <div className="w-full">
      {label && <p className="mb-1 text-xs text-muted-foreground">{label}</p>}
      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${height}`}
        className="h-auto w-full text-foreground"
        role="img"
        aria-label={label ?? "Line chart"}
      >
        {gridYs.map((y) => (
          <line
            key={y}
            x1={PAD.left}
            x2={VIEW_WIDTH - PAD.right}
            y1={y}
            y2={y}
            stroke="currentColor"
            strokeOpacity={0.08}
            strokeWidth={1}
          />
        ))}
        <path d={areaPath} fill={color} fillOpacity={0.08} stroke="none" />
        <path d={linePath} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => (
          <circle key={`${p.date}-${i}`} cx={p.x} cy={p.y} r={2} fill={color}>
            <title>{`${p.date}: ${data[i].value ?? 0}`}</title>
          </circle>
        ))}
        <g fontSize={9} fill="currentColor" fillOpacity={0.45}>
          <text x={2} y={PAD.top + 6}>
            {Math.round(max)}
          </text>
          <text x={2} y={baseY}>
            {Math.round(min)}
          </text>
          <text x={PAD.left} y={height - 4} textAnchor="start">
            {first}
          </text>
          <text x={VIEW_WIDTH - PAD.right} y={height - 4} textAnchor="end">
            {last}
          </text>
        </g>
      </svg>
    </div>
  );
}

type BarListProps = {
  items: Record<string, unknown>[];
  valueKey?: string;
  labelKey?: string;
  emptyText?: string;
  color?: string;
  maxItems?: number;
};

function toNumber(v: unknown): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

export function BarList({
  items,
  valueKey = "count",
  labelKey = "name",
  emptyText = "No data",
  color = CHART_COLORS.blue,
  maxItems = 10,
}: BarListProps) {
  if (!items || items.length === 0) {
    return <p className="text-xs text-muted-foreground/60">{emptyText}</p>;
  }

  const rows = items.slice(0, maxItems);
  const max = Math.max(1, ...rows.map((r) => toNumber(r[valueKey])));

  return (
    <div className="flex flex-col gap-1.5">
      {rows.map((row, i) => {
        const value = toNumber(row[valueKey]);
        const rawLabel = row[labelKey];
        const text = rawLabel === undefined || rawLabel === null || rawLabel === "" ? "—" : String(rawLabel);
        const pct = Math.max(0, Math.min(100, (value / max) * 100));
        return (
          <div key={`${text}-${i}`} className="grid grid-cols-[1fr_auto] items-center gap-2">
            <div className="relative h-6 overflow-hidden rounded-sm bg-muted/60">
              <div
                className="absolute inset-y-0 left-0 transition-[width] duration-500 ease-out"
                style={{ width: `${pct}%`, backgroundColor: `color-mix(in srgb, ${color} 18%, transparent)` }}
              />
              <span className="absolute inset-0 flex items-center truncate px-2 text-xs" title={text}>
                <span className="truncate">{text}</span>
              </span>
            </div>
            <span className="min-w-[3ch] text-right text-xs tabular-nums text-muted-foreground">{value}</span>
          </div>
        );
      })}
    </div>
  );
}
