"use client";

import { StatusChip } from "@/components/ui/status-chip";

type ChartDatum = {
  date: string;
  [key: string]: string | number | null | undefined;
};

type ChartSeries = {
  key: string;
  label: string;
  color: string;
  formatter?: (value: number) => string;
};

type LineChartCardProps = {
  title: string;
  caption: string;
  points: ChartDatum[];
  series: ChartSeries[];
  statusLabel?: string;
  statusTone?: "good" | "neutral" | "warning" | "bad";
  isLoading?: boolean;
  error?: unknown;
};

const WIDTH = 920;
const HEIGHT = 300;
const PAD_X = 42;
const PAD_TOP = 28;
const PAD_BOTTOM = 42;

export function LineChartCard({
  title,
  caption,
  points,
  series,
  statusLabel,
  statusTone = "neutral",
  isLoading,
  error
}: LineChartCardProps) {
  const numericValues = points.flatMap((point) =>
    series
      .map((item) => toNumber(point[item.key]))
      .filter((value): value is number => value !== null)
  );
  const min = numericValues.length ? Math.min(...numericValues) : 0;
  const max = numericValues.length ? Math.max(...numericValues) : 1;
  const span = max - min || Math.max(1, Math.abs(max));
  const yMin = min - span * 0.08;
  const yMax = max + span * 0.08;
  const latest = points.at(-1);
  const hasError = Boolean(error);
  const empty = !isLoading && (!points.length || !numericValues.length);

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-4">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="text-sm leading-5 text-[#a0a7b4]">{caption}</p>
        </div>
        {statusLabel && <StatusChip tone={statusTone}>{statusLabel}</StatusChip>}
      </div>

      <div className="relative h-[320px] rounded border border-[#2d333d] bg-[#101318]">
        {isLoading && (
          <div className="absolute inset-0 grid place-items-center text-sm text-[#a0a7b4]">
            Daten werden geladen...
          </div>
        )}
        {hasError && (
          <div className="absolute inset-0 grid place-items-center px-4 text-center text-sm text-rose-200">
            Chart-Daten konnten nicht geladen werden.
          </div>
        )}
        {empty && !hasError && (
          <div className="absolute inset-0 grid place-items-center text-sm text-[#a0a7b4]">
            Keine Zeitreihe verfügbar.
          </div>
        )}
        {!isLoading && !hasError && !empty && (
          <svg className="size-full" preserveAspectRatio="none" role="img" viewBox={`0 0 ${WIDTH} ${HEIGHT}`}>
            <defs>
              <linearGradient id={`grid-${title}`} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="#202630" />
                <stop offset="100%" stopColor="#12161d" />
              </linearGradient>
            </defs>
            <rect fill={`url(#grid-${title})`} height={HEIGHT} width={WIDTH} />
            {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
              <line
                key={ratio}
                stroke="#2d333d"
                strokeDasharray="4 8"
                strokeWidth="1"
                x1={PAD_X}
                x2={WIDTH - PAD_X}
                y1={PAD_TOP + ratio * (HEIGHT - PAD_TOP - PAD_BOTTOM)}
                y2={PAD_TOP + ratio * (HEIGHT - PAD_TOP - PAD_BOTTOM)}
              />
            ))}
            {series.map((item) => {
              const path = buildPath(points, item.key, yMin, yMax);
              if (!path) return null;
              return (
                <path
                  key={item.key}
                  d={path}
                  fill="none"
                  stroke={item.color}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="3"
                  vectorEffect="non-scaling-stroke"
                />
              );
            })}
            <text fill="#7f8794" fontSize="12" x={PAD_X} y={HEIGHT - 16}>
              {points[0]?.date}
            </text>
            <text fill="#7f8794" fontSize="12" textAnchor="end" x={WIDTH - PAD_X} y={HEIGHT - 16}>
              {latest?.date}
            </text>
          </svg>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-3">
        {series.map((item) => {
          const value = latest ? toNumber(latest[item.key]) : null;
          return (
            <div key={item.key} className="flex items-center gap-2 text-sm text-[#c9d0da]">
              <span className="size-2 rounded-full" style={{ backgroundColor: item.color }} />
              <span className="text-[#a0a7b4]">{item.label}</span>
              <span className="tabular-nums">{value === null ? "-" : (item.formatter?.(value) ?? value.toFixed(2))}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function buildPath(points: ChartDatum[], key: string, yMin: number, yMax: number) {
  const values = points
    .map((point, index) => ({ index, value: toNumber(point[key]) }))
    .filter((point): point is { index: number; value: number } => point.value !== null);
  if (values.length < 2) return "";

  return values
    .map((point, pathIndex) => {
      const x = xForIndex(point.index, points.length);
      const y = yForValue(point.value, yMin, yMax);
      return `${pathIndex === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function xForIndex(index: number, total: number) {
  if (total <= 1) return PAD_X;
  return PAD_X + (index / (total - 1)) * (WIDTH - PAD_X * 2);
}

function yForValue(value: number, yMin: number, yMax: number) {
  const chartHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const ratio = (value - yMin) / (yMax - yMin || 1);
  return PAD_TOP + (1 - ratio) * chartHeight;
}

function toNumber(value: string | number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return value;
}
