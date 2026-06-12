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

export type ChartLevel = {
  key: string;
  label: string;
  value: number;
  color: string;
};

export type ChartMarker = {
  key: string;
  date: string;
  label: string;
  value?: number | null;
  color: string;
};

type LineChartCardProps = {
  title: string;
  caption: string;
  points: ChartDatum[];
  series: ChartSeries[];
  chartMode?: "line" | "candlestick";
  levels?: ChartLevel[];
  markers?: ChartMarker[];
  subSeries?: ChartSeries[];
  subTitle?: string;
  volumeKey?: string;
  volumeLabel?: string;
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
  chartMode = "line",
  levels = [],
  markers = [],
  subSeries = [],
  subTitle = "",
  volumeKey,
  volumeLabel = "Volumen",
  statusLabel,
  statusTone = "neutral",
  isLoading,
  error
}: LineChartCardProps) {
  const hasSubChart = subSeries.length > 0;
  const subTop = hasSubChart ? HEIGHT - PAD_BOTTOM - 64 : HEIGHT - PAD_BOTTOM;
  const priceBottom = hasSubChart ? subTop - 14 : HEIGHT - PAD_BOTTOM;
  const numericValues = points.flatMap((point) =>
    series
      .map((item) => toNumber(point[item.key]))
      .filter((value): value is number => value !== null)
  );
  const candleValues =
    chartMode === "candlestick"
      ? points.flatMap((point) =>
          ["open", "high", "low", "close"]
            .map((key) => toNumber(point[key]))
            .filter((value): value is number => value !== null)
        )
      : [];
  const levelValues = levels.map((level) => level.value).filter((value) => Number.isFinite(value));
  const allValues = [...numericValues, ...candleValues, ...levelValues];
  const min = allValues.length ? Math.min(...allValues) : 0;
  const max = allValues.length ? Math.max(...allValues) : 1;
  const span = max - min || Math.max(1, Math.abs(max));
  const yMin = min - span * 0.08;
  const yMax = max + span * 0.08;
  const subValues = points.flatMap((point) =>
    subSeries
      .map((item) => toNumber(point[item.key]))
      .filter((value): value is number => value !== null)
  );
  const subMin = subValues.length ? Math.min(...subValues) : 0;
  const subMax = subValues.length ? Math.max(...subValues) : 1;
  const subSpan = subMax - subMin || Math.max(1, Math.abs(subMax));
  const subYMin = subMin - subSpan * 0.08;
  const subYMax = subMax + subSpan * 0.08;
  const volumeValues = volumeKey
    ? points.map((point) => toNumber(point[volumeKey])).filter((value): value is number => value !== null)
    : [];
  const maxVolume = volumeValues.length ? Math.max(...volumeValues) : 0;
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
                y1={PAD_TOP + ratio * (priceBottom - PAD_TOP)}
                y2={PAD_TOP + ratio * (priceBottom - PAD_TOP)}
              />
            ))}
            {volumeKey && maxVolume > 0 && (
              <g opacity="0.24">
                {points.map((point, index) => {
                  const volume = toNumber(point[volumeKey]);
                  if (volume === null) return null;
                  const barHeight = Math.max(1, (volume / maxVolume) * 54);
                  const barWidth = Math.max(2, (WIDTH - PAD_X * 2) / Math.max(1, points.length) * 0.72);
                  const x = xForIndex(index, points.length) - barWidth / 2;
                  const y = priceBottom - barHeight;
                  const close = toNumber(point.close);
                  const open = toNumber(point.open);
                  const fill = close !== null && open !== null && close < open ? "#fb7185" : "#34d399";
                  return <rect key={`${point.date}-${index}`} fill={fill} height={barHeight} width={barWidth} x={x} y={y} />;
                })}
              </g>
            )}
            {chartMode === "candlestick" && (
              <g>
                {points.map((point, index) => {
                  const open = toNumber(point.open);
                  const high = toNumber(point.high);
                  const low = toNumber(point.low);
                  const close = toNumber(point.close);
                  if (open === null || high === null || low === null || close === null) return null;
                  const x = xForIndex(index, points.length);
                  const candleWidth = Math.max(3, (WIDTH - PAD_X * 2) / Math.max(1, points.length) * 0.58);
                  const yHigh = yForValue(high, yMin, yMax, PAD_TOP, priceBottom);
                  const yLow = yForValue(low, yMin, yMax, PAD_TOP, priceBottom);
                  const yOpen = yForValue(open, yMin, yMax, PAD_TOP, priceBottom);
                  const yClose = yForValue(close, yMin, yMax, PAD_TOP, priceBottom);
                  const up = close >= open;
                  const color = up ? "#34d399" : "#fb7185";
                  const bodyY = Math.min(yOpen, yClose);
                  const bodyHeight = Math.max(1.4, Math.abs(yClose - yOpen));
                  return (
                    <g key={`${point.date}-candle`}>
                      <line
                        stroke={color}
                        strokeWidth="1.4"
                        vectorEffect="non-scaling-stroke"
                        x1={x}
                        x2={x}
                        y1={yHigh}
                        y2={yLow}
                      />
                      <rect
                        fill={up ? "#34d399" : "#101318"}
                        height={bodyHeight}
                        stroke={color}
                        strokeWidth="1.5"
                        vectorEffect="non-scaling-stroke"
                        width={candleWidth}
                        x={x - candleWidth / 2}
                        y={bodyY}
                      />
                    </g>
                  );
                })}
              </g>
            )}
            {series.map((item) => {
              const path = buildPath(points, item.key, yMin, yMax, PAD_TOP, priceBottom);
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
            {levels.map((level) => {
              const y = yForValue(level.value, yMin, yMax, PAD_TOP, priceBottom);
              return (
                <g key={level.key}>
                  <line
                    stroke={level.color}
                    strokeDasharray="7 7"
                    strokeWidth="2"
                    vectorEffect="non-scaling-stroke"
                    x1={PAD_X}
                    x2={WIDTH - PAD_X}
                    y1={y}
                    y2={y}
                  />
                  <rect fill="#101318" height="18" opacity="0.88" rx="3" width="168" x={PAD_X + 8} y={y - 22} />
                  <text fill={level.color} fontSize="12" fontWeight="700" x={PAD_X + 14} y={y - 9}>
                    {level.label}: {level.value.toFixed(2)}
                  </text>
                </g>
              );
            })}
            {markers.slice(0, 8).map((marker) => {
              const markerIndex = indexForDate(points, marker.date);
              if (markerIndex < 0) return null;
              const point = points[markerIndex];
              const markerValue = toNumber(marker.value) ?? toNumber(point.close);
              if (markerValue === null) return null;
              const x = xForIndex(markerIndex, points.length);
              const y = yForValue(markerValue, yMin, yMax, PAD_TOP, priceBottom);
              return (
                <g key={marker.key}>
                  <line
                    opacity="0.55"
                    stroke={marker.color}
                    strokeDasharray="3 7"
                    strokeWidth="1.5"
                    vectorEffect="non-scaling-stroke"
                    x1={x}
                    x2={x}
                    y1={PAD_TOP}
                    y2={priceBottom}
                  />
                  <circle cx={x} cy={y} fill={marker.color} r="5" vectorEffect="non-scaling-stroke" />
                  <text fill={marker.color} fontSize="11" fontWeight="700" textAnchor="middle" x={x} y={Math.max(18, y - 10)}>
                    {truncateLabel(marker.label)}
                  </text>
                </g>
              );
            })}
            {hasSubChart && (
              <g>
                <line stroke="#2d333d" strokeWidth="1" x1={PAD_X} x2={WIDTH - PAD_X} y1={subTop} y2={subTop} />
                {subTitle && (
                  <text fill="#a0a7b4" fontSize="11" fontWeight="700" x={PAD_X} y={subTop + 14}>
                    {subTitle}
                  </text>
                )}
                {subSeries.map((item) => {
                  const path = buildPath(points, item.key, subYMin, subYMax, subTop + 18, HEIGHT - PAD_BOTTOM);
                  if (!path) return null;
                  return (
                    <path
                      key={item.key}
                      d={path}
                      fill="none"
                      stroke={item.color}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      vectorEffect="non-scaling-stroke"
                    />
                  );
                })}
              </g>
            )}
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
        {volumeKey && (
          <div className="flex items-center gap-2 text-sm text-[#c9d0da]">
            <span className="size-2 rounded-full bg-[#697386]" />
            <span className="text-[#a0a7b4]">{volumeLabel}</span>
            <span className="tabular-nums">{formatCompact(toNumber(latest?.[volumeKey]))}</span>
          </div>
        )}
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
        {subSeries.map((item) => {
          const value = latest ? toNumber(latest[item.key]) : null;
          return (
            <div key={item.key} className="flex items-center gap-2 text-sm text-[#c9d0da]">
              <span className="size-2 rounded-full" style={{ backgroundColor: item.color }} />
              <span className="text-[#a0a7b4]">{item.label}</span>
              <span className="tabular-nums">{value === null ? "-" : (item.formatter?.(value) ?? value.toFixed(2))}</span>
            </div>
          );
        })}
        {levels.map((level) => (
          <div key={level.key} className="flex items-center gap-2 text-sm text-[#c9d0da]">
            <span className="h-px w-4 border-t border-dashed" style={{ borderColor: level.color }} />
            <span className="text-[#a0a7b4]">{level.label}</span>
            <span className="tabular-nums">{level.value.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function buildPath(
  points: ChartDatum[],
  key: string,
  yMin: number,
  yMax: number,
  top: number,
  bottom: number
) {
  const values = points
    .map((point, index) => ({ index, value: toNumber(point[key]) }))
    .filter((point): point is { index: number; value: number } => point.value !== null);
  if (values.length < 2) return "";

  return values
    .map((point, pathIndex) => {
      const x = xForIndex(point.index, points.length);
      const y = yForValue(point.value, yMin, yMax, top, bottom);
      return `${pathIndex === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function xForIndex(index: number, total: number) {
  if (total <= 1) return PAD_X;
  return PAD_X + (index / (total - 1)) * (WIDTH - PAD_X * 2);
}

function yForValue(value: number, yMin: number, yMax: number, top: number, bottom: number) {
  const chartHeight = bottom - top;
  const ratio = (value - yMin) / (yMax - yMin || 1);
  return top + (1 - ratio) * chartHeight;
}

function indexForDate(points: ChartDatum[], date: string) {
  const exact = points.findIndex((point) => point.date === date);
  if (exact >= 0) return exact;
  const targetTime = Date.parse(date);
  if (Number.isNaN(targetTime)) return -1;
  let bestIndex = -1;
  let bestDistance = Number.POSITIVE_INFINITY;
  points.forEach((point, index) => {
    const pointTime = Date.parse(point.date);
    if (Number.isNaN(pointTime)) return;
    const distance = Math.abs(pointTime - targetTime);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestDistance <= 1000 * 60 * 60 * 24 * 7 ? bestIndex : -1;
}

function toNumber(value: string | number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return value;
}

function truncateLabel(label: string) {
  return label.length > 18 ? `${label.slice(0, 17)}...` : label;
}

function formatCompact(value: number | null) {
  if (value === null) return "-";
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)} Mrd.`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} Mio.`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} Tsd.`;
  return value.toFixed(0);
}
