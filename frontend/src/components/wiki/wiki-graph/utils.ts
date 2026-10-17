// Small geometry and palette helpers for the wiki graph.

const SCOPE_PALETTE = ["#c9a27e", "#b8786a", "#8fa98b", "#8f9fc0", "#b59ac2", "#c7b36f"];

/** Cycles through six soft colours. */
export function scopeColor(idx: number): string {
  const n = SCOPE_PALETTE.length;
  return SCOPE_PALETTE[((Math.trunc(idx) % n) + n) % n];
}

/** Node radius grows with the square root of the degree, clamped per mode. */
export function nodeRadius(degree: number, mini = false): number {
  const d = Math.max(0, degree || 0);
  if (mini) return Math.min(6, Math.max(3, 3 + Math.sqrt(d) * 1.2));
  return Math.min(18, Math.max(5, 5 + Math.sqrt(d) * 3));
}

export type Point = { x: number; y: number };

function cross(o: Point, a: Point, b: Point): number {
  return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
}

/** Convex hull (monotone chain), counter-clockwise, without repeating the first point. */
export function convexHull(points: Point[]): Point[] {
  const pts = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  if (pts.length <= 2) return pts;
  // Build one half-hull: keep only left turns while sweeping through `seq`.
  const halfHull = (seq: Iterable<Point>): Point[] => {
    const chain: Point[] = [];
    for (const next of seq) {
      let n = chain.length;
      while (n >= 2 && cross(chain[n - 2], chain[n - 1], next) <= 0) {
        chain.pop();
        n = chain.length;
      }
      chain.push(next);
    }
    // The last point of each half is the first point of the other.
    chain.pop();
    return chain;
  };
  return [...halfHull(pts), ...halfHull([...pts].reverse())];
}

/**
 * Rounded outline around a hull, pushed outward by `padding`. Returns an SVG path string
 * (also usable with `new Path2D(path)` on canvas).
 */
export function hullToPath(hull: Point[], padding = 10): string {
  if (hull.length === 0) return "";
  if (hull.length === 1) {
    const { x, y } = hull[0];
    const r = padding;
    return `M ${x - r} ${y} a ${r} ${r} 0 1 0 ${2 * r} 0 a ${r} ${r} 0 1 0 ${-2 * r} 0 Z`;
  }
  const cx = hull.reduce((s, p) => s + p.x, 0) / hull.length;
  const cy = hull.reduce((s, p) => s + p.y, 0) / hull.length;
  const expanded = hull.map((p) => {
    const dx = p.x - cx;
    const dy = p.y - cy;
    const len = Math.hypot(dx, dy) || 1;
    return { x: p.x + (dx / len) * padding, y: p.y + (dy / len) * padding };
  });
  const n = expanded.length;
  const mid = (a: Point, b: Point): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  const start = mid(expanded[n - 1], expanded[0]);
  let d = `M ${start.x} ${start.y}`;
  for (let i = 0; i < n; i++) {
    const corner = expanded[i];
    const next = mid(corner, expanded[(i + 1) % n]);
    d += ` Q ${corner.x} ${corner.y} ${next.x} ${next.y}`;
  }
  return `${d} Z`;
}
