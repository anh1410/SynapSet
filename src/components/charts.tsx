/**
 * Small dependency-free chart kit for the performance dashboard.
 *
 * Conventions (kept deliberately few):
 * - Magnitude is one hue: the app's primary. Status (strong / developing /
 *   needs support) uses the reserved success/warning/destructive tokens and
 *   always ships with an icon + text label, never colour alone.
 * - Marks are thin (bars <= 12px, lines 2px, 8px markers with a surface ring),
 *   grid/axes are solid hairlines, text wears text tokens - never series colour.
 * - Every chart has a table view (ChartCard) and a hover/focus tooltip.
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, BarChart3, CheckCircle2, CircleDashed, Table2, TrendingUp } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BAND_LABELS, type Band } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Accent (the app's --primary) and the de-emphasis grey for context series.
 *  Validated together on the light surface (contrast >= 3:1, CVD dE > 17). */
export const SERIES_ACCENT = "#463acb";
export const SERIES_CONTEXT = "#7c8799";

export function fmtPct(value: number | null | undefined, digits = 0): string {
  return value == null ? "—" : `${value.toFixed(digits)}%`;
}

// ---------- status ----------

const bandVariant: Record<Band, "success" | "warning" | "destructive" | "outline"> = {
  strong: "success",
  developing: "warning",
  needs_support: "destructive",
  insufficient: "outline",
};
const bandIcon = {
  strong: CheckCircle2,
  developing: TrendingUp,
  needs_support: AlertTriangle,
  insufficient: CircleDashed,
} as const;

export function BandBadge({ band, className }: { band: Band; className?: string }) {
  const Icon = bandIcon[band];
  return (
    <Badge variant={bandVariant[band]} className={className}>
      <Icon className="h-3 w-3" /> {BAND_LABELS[band]}
    </Badge>
  );
}

// ---------- card with chart/table toggle ----------

export function ChartCard({
  title,
  description,
  icon: Icon,
  table,
  children,
  className,
  empty,
}: {
  title: string;
  description?: string;
  icon?: typeof BarChart3;
  table?: ReactNode;
  children: ReactNode;
  className?: string;
  empty?: string | null;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <Card className={className}>
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {Icon && <Icon className="h-4 w-4 text-primary" />}
            <CardTitle>{title}</CardTitle>
          </div>
          {description && <CardDescription className="mt-1">{description}</CardDescription>}
        </div>
        {table && !empty && (
          <div className="flex shrink-0 rounded-md border border-border p-0.5" role="group" aria-label="View">
            {(["chart", "table"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                aria-pressed={view === v}
                title={v === "chart" ? "Chart view" : "Table view"}
                className={cn(
                  "rounded px-1.5 py-1 text-muted-foreground transition-colors",
                  view === v ? "bg-secondary text-foreground" : "hover:text-foreground"
                )}
              >
                {v === "chart" ? <BarChart3 className="h-3.5 w-3.5" /> : <Table2 className="h-3.5 w-3.5" />}
              </button>
            ))}
          </div>
        )}
      </CardHeader>
      <CardContent>
        {empty ? (
          <p className="py-6 text-center text-xs text-muted-foreground">{empty}</p>
        ) : view === "table" && table ? (
          table
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

export function DataTable({ headers, rows }: { headers: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            {headers.map((h, i) => (
              <th key={h} className={cn("py-2 pr-3 font-medium", i > 0 && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((cells, r) => (
            <tr key={r}>
              {cells.map((c, i) => (
                <td key={i} className={cn("py-2 pr-3 text-foreground", i > 0 && "text-right tabular-nums")}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------- horizontal percentage bars ----------

export interface BarRow {
  key: string;
  label: string;
  percent: number | null;
  /** Secondary line shown in the tooltip, e.g. "18 / 24 marks · 6 answers". */
  detail?: string;
  band?: Band;
}

/** One series, magnitude 0-100%: a thin bar per row, value at the tip,
 *  band as a labelled badge. Rows with no graded evidence show a dash. */
export function PercentBars({ rows, showBands = true }: { rows: BarRow[]; showBands?: boolean }) {
  const [active, setActive] = useState<string | null>(null);
  return (
    <ul className="space-y-2.5">
      {rows.map((row) => (
        <li
          key={row.key}
          tabIndex={0}
          onMouseEnter={() => setActive(row.key)}
          onMouseLeave={() => setActive(null)}
          onFocus={() => setActive(row.key)}
          onBlur={() => setActive(null)}
          className="relative rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="truncate text-xs font-medium text-foreground">{row.label}</span>
            <div className="flex shrink-0 items-center gap-2">
              {showBands && row.band && <BandBadge band={row.band} />}
              <span className="w-10 text-right text-xs font-semibold tabular-nums text-foreground">
                {fmtPct(row.percent)}
              </span>
            </div>
          </div>
          <div className="h-2 w-full rounded-full bg-secondary">
            {row.percent != null && (
              <div
                className="h-2 rounded-full transition-all duration-500"
                style={{ width: `${Math.max(row.percent, 1)}%`, backgroundColor: SERIES_ACCENT }}
              />
            )}
          </div>
          {active === row.key && row.detail && (
            <div className="pointer-events-none absolute right-0 top-full z-20 mt-1 rounded-md border border-border bg-white px-2.5 py-1.5 text-[11px] text-foreground shadow-card">
              <span className="font-medium">{row.label}</span> · {row.detail}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

// ---------- column chart (counts per ordered bucket) ----------

export interface ColumnDatum {
  key: string;
  label: string;
  value: number;
  tooltip: string;
}

export function ColumnChart({ data, height = 140 }: { data: ColumnDatum[]; height?: number }) {
  const [active, setActive] = useState<string | null>(null);
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div>
      <div className="relative flex items-end gap-1 border-b border-border" style={{ height }}>
        {data.map((d) => {
          const h = (d.value / max) * (height - 20);
          return (
            <div
              key={d.key}
              tabIndex={0}
              onMouseEnter={() => setActive(d.key)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(d.key)}
              onBlur={() => setActive(null)}
              className="relative flex h-full flex-1 flex-col items-center justify-end outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {d.value > 0 && <span className="mb-0.5 text-[10px] font-medium tabular-nums text-foreground">{d.value}</span>}
              <div
                className="w-full max-w-[24px] rounded-t transition-all duration-500"
                style={{ height: Math.max(h, d.value > 0 ? 3 : 0), backgroundColor: SERIES_ACCENT, opacity: active && active !== d.key ? 0.45 : 1 }}
              />
              {active === d.key && (
                <div className="pointer-events-none absolute bottom-full z-20 mb-1 whitespace-nowrap rounded-md border border-border bg-white px-2 py-1 text-[11px] text-foreground shadow-card">
                  {d.tooltip}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex gap-1">
        {data.map((d) => (
          <span key={d.key} className="flex-1 truncate text-center text-[10px] text-muted-foreground">
            {d.label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------- trend line (percent over assessments) ----------

export interface TrendSeries {
  name: string;
  color: string;
  values: (number | null)[];
  emphasis?: boolean;
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Percent (0-100, one axis) across assessments in date order. With a context
 *  series (class average) the emphasised series is accent, context is grey. */
export function TrendChart({ labels, series, height = 180 }: { labels: string[]; series: TrendSeries[]; height?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const pad = { l: 34, r: 16, t: 12, b: 26 };
  const plotW = Math.max(width - pad.l - pad.r, 10);
  const plotH = height - pad.t - pad.b;
  const n = labels.length;
  const x = (i: number) => pad.l + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (v: number) => pad.t + plotH - (v / 100) * plotH;

  const pathFor = (values: (number | null)[]) => {
    let d = "";
    let pen = false;
    values.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
      pen = true;
    });
    return d.trim();
  };

  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const rect = (e.currentTarget as SVGRectElement).getBoundingClientRect();
    const px = e.clientX - rect.left;
    const i = n <= 1 ? 0 : Math.round((px / rect.width) * (n - 1));
    setActive(Math.min(Math.max(i, 0), n - 1));
  };

  const ordered = [...series].sort((a, b) => Number(!!a.emphasis) - Number(!!b.emphasis)); // accent drawn last

  return (
    <div>
      {series.length > 1 && (
        <div className="mb-2 flex flex-wrap gap-3">
          {series.map((s) => (
            <span key={s.name} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <span className="h-0.5 w-4 rounded-full" style={{ backgroundColor: s.color }} /> {s.name}
            </span>
          ))}
        </div>
      )}
      <div ref={ref} className="relative w-full" style={{ height }}>
        {width > 0 && (
          <svg width={width} height={height} className="overflow-visible">
            {[0, 50, 100].map((t) => (
              <g key={t}>
                <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} stroke="hsl(var(--border))" strokeWidth={1} />
                <text x={pad.l - 6} y={y(t) + 3} textAnchor="end" className="fill-muted-foreground text-[10px] tabular-nums">
                  {t}%
                </text>
              </g>
            ))}
            {labels.map((l, i) => (
              <text
                key={i}
                x={x(i)}
                y={height - 8}
                textAnchor={n > 1 && i === 0 ? "start" : n > 1 && i === n - 1 ? "end" : "middle"}
                className="fill-muted-foreground text-[10px]"
              >
                {l.length > 16 ? `${l.slice(0, 15)}…` : l}
              </text>
            ))}
            {active != null && (
              <line x1={x(active)} x2={x(active)} y1={pad.t} y2={pad.t + plotH} stroke="hsl(var(--border))" strokeWidth={1} />
            )}
            {ordered.map((s) => (
              <g key={s.name}>
                <path d={pathFor(s.values)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                {s.values.map((v, i) =>
                  v == null ? null : (
                    <circle key={i} cx={x(i)} cy={y(v)} r={active === i ? 5 : 4} fill={s.color} stroke="white" strokeWidth={2} />
                  )
                )}
              </g>
            ))}
            {/* Direct label on the emphasised series' last point. */}
            {series
              .filter((s) => s.emphasis)
              .map((s) => {
                const last = s.values.map((v, i) => [v, i] as const).filter(([v]) => v != null).pop();
                if (!last || active != null) return null;
                return (
                  <text
                    key={s.name}
                    x={x(last[1])}
                    y={y(last[0]!) - 10}
                    textAnchor={last[1] === n - 1 && n > 1 ? "end" : "middle"}
                    className="fill-foreground text-[11px] font-semibold"
                  >
                    {fmtPct(last[0])}
                  </text>
                );
              })}
            <rect
              x={pad.l}
              y={pad.t}
              width={plotW}
              height={plotH}
              fill="transparent"
              onMouseMove={onMove}
              onMouseLeave={() => setActive(null)}
            />
          </svg>
        )}
        {active != null && width > 0 && (
          <div
            className="pointer-events-none absolute top-0 z-20 min-w-[140px] rounded-md border border-border bg-white px-2.5 py-1.5 text-[11px] shadow-card"
            style={{ left: Math.min(Math.max(x(active) - 70, 0), width - 150) }}
          >
            <p className="mb-0.5 font-medium text-foreground">{labels[active]}</p>
            {series.map((s) => (
              <p key={s.name} className="flex items-center justify-between gap-3 text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} /> {s.name}
                </span>
                <span className="font-medium tabular-nums text-foreground">{fmtPct(s.values[active])}</span>
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------- stat tile ----------

export function StatTile({
  label,
  value,
  sub,
  icon: Icon,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: typeof BarChart3;
  tone?: "warning";
}) {
  return (
    <Card className={cn(tone === "warning" && "border-warning/30 bg-warning/[0.03]")}>
      <CardContent className="p-4">
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {Icon && <Icon className="h-3.5 w-3.5" />} {label}
        </p>
        <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
        {sub && <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}
