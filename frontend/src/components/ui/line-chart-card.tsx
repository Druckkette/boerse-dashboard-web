"use client";

import { Eye, EyeOff, Minus, Plus, RotateCcw } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, WheelEvent as ReactWheelEvent } from "react";
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
  dateTickMode?: "ends" | "weekly";
  showHorizontalGrid?: boolean;
  isLoading?: boolean;
  error?: unknown;
  hideTextHeader?: boolean;
};

const WIDTH = 920;
const HEIGHT = 300;
const PAD_X = 42;
const PAD_TOP = 28;
const PAD_BOTTOM = 42;
const MIN_VISIBLE_POINTS = 24;

type VisibleRange = {
  start: number;
  end: number;
  total: number;
};

type DragState = {
  pointerId: number;
  clientX: number;
  range: VisibleRange;
};

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
  dateTickMode = "ends",
  showHorizontalGrid = true,
  isLoading,
  error,
  hideTextHeader = false
}: LineChartCardProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const [visibleRange, setVisibleRange] = useState<VisibleRange>(() => ({
    start: 0,
    end: Math.max(0, points.length - 1),
    total: points.length
  }));
  const [hiddenSeries, setHiddenSeries] = useState<Record<string, boolean>>({});
  const normalizedRange = useMemo(
    () =>
      visibleRange.total === points.length
        ? clampVisibleRange(visibleRange, points.length)
        : fullVisibleRange(points.length),
    [points.length, visibleRange]
  );
  const visiblePoints = useMemo(
    () => points.slice(normalizedRange.start, normalizedRange.end + 1),
    [normalizedRange.end, normalizedRange.start, points]
  );
  const visibleSeries = useMemo(
    () => series.filter((item) => !hiddenSeries[item.key]),
    [hiddenSeries, series]
  );
  const visibleSubSeries = useMemo(
    () => subSeries.filter((item) => !hiddenSeries[item.key]),
    [hiddenSeries, subSeries]
  );
  const toggleSeries = useMemo(
    () => [
      ...series.map((item) => ({ ...item, panel: "main" as const })),
      ...subSeries.map((item) => ({ ...item, panel: "sub" as const }))
    ],
    [series, subSeries]
  );
  const isZoomed = points.length > 0 && (normalizedRange.start > 0 || normalizedRange.end < points.length - 1);
  const hasSubChart = subSeries.length > 0;
  const subTop = hasSubChart ? HEIGHT - PAD_BOTTOM - 64 : HEIGHT - PAD_BOTTOM;
  const priceBottom = hasSubChart ? subTop - 14 : HEIGHT - PAD_BOTTOM;
  const numericValues = visiblePoints.flatMap((point) =>
    visibleSeries
      .map((item) => toNumber(point[item.key]))
      .filter((value): value is number => value !== null)
  );
  const candleValues =
    chartMode === "candlestick"
      ? visiblePoints.flatMap((point) =>
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
  const subValues = visiblePoints.flatMap((point) =>
    visibleSubSeries
      .map((item) => toNumber(point[item.key]))
      .filter((value): value is number => value !== null)
  );
  const subMin = subValues.length ? Math.min(...subValues) : 0;
  const subMax = subValues.length ? Math.max(...subValues) : 1;
  const subSpan = subMax - subMin || Math.max(1, Math.abs(subMax));
  const subYMin = subMin - subSpan * 0.08;
  const subYMax = subMax + subSpan * 0.08;
  const volumeValues = volumeKey
    ? visiblePoints.map((point) => toNumber(point[volumeKey])).filter((value): value is number => value !== null)
    : [];
  const maxVolume = volumeValues.length ? Math.max(...volumeValues) : 0;
  const latest = visiblePoints.at(-1);
  const hasError = Boolean(error);
  const empty = !isLoading && (!visiblePoints.length || (!numericValues.length && !candleValues.length && !subValues.length));
  const currentWindow = normalizedRange.end - normalizedRange.start + 1;
  const minWindow = Math.min(MIN_VISIBLE_POINTS, points.length);
  const canZoomIn = points.length > 1 && currentWindow > minWindow;
  const canZoomOut = points.length > 1 && currentWindow < points.length;
  const hasDistributionMarkers = markers.some(isDistributionMarker);

  function handleWheel(event: ReactWheelEvent<HTMLDivElement>) {
    if (points.length <= 1) return;
    event.preventDefault();
    const rect = chartRef.current?.getBoundingClientRect();
    if (!rect?.width) return;
    const current = clampVisibleRange(normalizedRange, points.length);
    const currentWindow = current.end - current.start + 1;
    const minWindow = Math.min(MIN_VISIBLE_POINTS, points.length);
    const nextWindow = Math.max(
      minWindow,
      Math.min(points.length, Math.round(currentWindow * (event.deltaY > 0 ? 1.18 : 0.82)))
    );
    const cursorRatio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const anchor = current.start + cursorRatio * Math.max(1, currentWindow - 1);
    const nextStart = Math.round(anchor - cursorRatio * Math.max(1, nextWindow - 1));
    setVisibleRange(clampVisibleRange({ start: nextStart, end: nextStart + nextWindow - 1 }, points.length));
  }

  function zoomBy(factor: number) {
    if (points.length <= 1) return;
    const current = clampVisibleRange(normalizedRange, points.length);
    const windowSize = current.end - current.start + 1;
    const nextWindow = Math.max(
      minWindow,
      Math.min(points.length, Math.round(windowSize * factor))
    );
    const center = current.start + Math.max(1, windowSize - 1) / 2;
    const nextStart = Math.round(center - Math.max(1, nextWindow - 1) / 2);
    setVisibleRange(clampVisibleRange({ start: nextStart, end: nextStart + nextWindow - 1 }, points.length));
  }

  function toggleLine(key: string) {
    setHiddenSeries((current) => ({ ...current, [key]: !current[key] }));
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (points.length <= MIN_VISIBLE_POINTS) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      range: normalizedRange
    };
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const rect = chartRef.current?.getBoundingClientRect();
    if (!rect?.width) return;
    const windowSize = drag.range.end - drag.range.start + 1;
    const pointsPerPixel = windowSize / rect.width;
    const offset = Math.round((drag.clientX - event.clientX) * pointsPerPixel);
    setVisibleRange(
      clampVisibleRange(
        { start: drag.range.start + offset, end: drag.range.end + offset },
        points.length
      )
    );
  }

  function handlePointerEnd(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null;
    }
  }

  return (
    <section className="rounded-[24px] border border-[#e3e8ef] bg-white p-5 shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
      <div className={hideTextHeader ? "mb-3 flex justify-end" : "mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between"}>
        {!hideTextHeader && (
          <div>
            <h2 className="text-lg font-semibold text-[#172033]">{title}</h2>
            <p className="mt-1 text-sm leading-6 text-[#687386]">{caption}</p>
          </div>
        )}
        <div className="flex items-center gap-2">
          <button
            className="inline-flex size-9 items-center justify-center rounded-full border border-[#d8e1ea] bg-white text-[#172033] shadow-sm transition hover:border-[#0f766e] disabled:cursor-not-allowed disabled:opacity-45"
            type="button"
            title="In den Chart hineinzoomen"
            aria-label="In den Chart hineinzoomen"
            disabled={!canZoomIn}
            onClick={() => zoomBy(0.72)}
          >
            <Plus size={15} />
          </button>
          <button
            className="inline-flex size-9 items-center justify-center rounded-full border border-[#d8e1ea] bg-white text-[#172033] shadow-sm transition hover:border-[#0f766e] disabled:cursor-not-allowed disabled:opacity-45"
            type="button"
            title="Aus dem Chart herauszoomen"
            aria-label="Aus dem Chart herauszoomen"
            disabled={!canZoomOut}
            onClick={() => zoomBy(1.38)}
          >
            <Minus size={15} />
          </button>
          <button
            className="inline-flex size-9 items-center justify-center rounded-full border border-[#d8e1ea] bg-white text-[#172033] shadow-sm transition hover:border-[#0f766e] disabled:cursor-not-allowed disabled:opacity-45"
            type="button"
            title="Chart zurücksetzen"
            aria-label="Chart zurücksetzen"
            disabled={!isZoomed}
            onClick={() => setVisibleRange(fullVisibleRange(points.length))}
          >
            <RotateCcw size={15} />
          </button>
          {!hideTextHeader && statusLabel && <StatusChip tone={statusTone}>{statusLabel}</StatusChip>}
        </div>
      </div>

      <div
        ref={chartRef}
        className="relative h-[320px] touch-none select-none rounded-[20px] border border-[#d9dee8] bg-white"
        onPointerCancel={handlePointerEnd}
        onPointerDown={handlePointerDown}
        onPointerLeave={handlePointerEnd}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onWheel={handleWheel}
      >
        {isLoading && (
          <div className="absolute inset-0 grid place-items-center text-sm text-[#687386]">
            Daten werden geladen...
          </div>
        )}
        {hasError && (
          <div className="absolute inset-0 grid place-items-center px-4 text-center text-sm font-medium text-[#c2413b]">
            Chart-Daten konnten nicht geladen werden.
          </div>
        )}
        {empty && !hasError && (
          <div className="absolute inset-0 grid place-items-center text-sm text-[#687386]">
            Keine Zeitreihe verfügbar.
          </div>
        )}
        {!isLoading && !hasError && !empty && (
          <svg className="size-full" preserveAspectRatio="none" role="img" viewBox={`0 0 ${WIDTH} ${HEIGHT}`}>
            <rect fill="#ffffff" height={HEIGHT} width={WIDTH} />
            {showHorizontalGrid &&
              [0.2, 0.4, 0.6, 0.8].map((ratio) => (
                <line
                  key={ratio}
                  stroke="#d9dee8"
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
                {visiblePoints.map((point, index) => {
                  const volume = toNumber(point[volumeKey]);
                  if (volume === null) return null;
                  const barHeight = Math.max(1, (volume / maxVolume) * 54);
                  const barWidth = Math.max(2, (WIDTH - PAD_X * 2) / Math.max(1, visiblePoints.length) * 0.72);
                  const x = xForIndex(index, visiblePoints.length) - barWidth / 2;
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
                {visiblePoints.map((point, index) => {
                  const open = toNumber(point.open);
                  const high = toNumber(point.high);
                  const low = toNumber(point.low);
                  const close = toNumber(point.close);
                  if (open === null || high === null || low === null || close === null) return null;
                  const x = xForIndex(index, visiblePoints.length);
                  const candleWidth = Math.max(3, (WIDTH - PAD_X * 2) / Math.max(1, visiblePoints.length) * 0.58);
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
                        fill={up ? "#34d399" : "#fb7185"}
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
            {visibleSeries.map((item) => {
              const path = buildPath(visiblePoints, item.key, yMin, yMax, PAD_TOP, priceBottom);
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
                  <rect fill="#ffffff" height="18" opacity="0.9" rx="3" width="168" x={PAD_X + 8} y={y - 22} />
                  <text fill={level.color} fontSize="12" fontWeight="700" x={PAD_X + 14} y={y - 9}>
                    {level.label}: {level.value.toFixed(2)}
                  </text>
                </g>
              );
            })}
            {markers.slice(0, 8).map((marker) => {
              const markerIndex = indexForDate(visiblePoints, marker.date);
              if (markerIndex < 0) return null;
              const point = visiblePoints[markerIndex];
              const markerValue = toNumber(marker.value) ?? toNumber(point.close);
              if (markerValue === null) return null;
              const x = xForIndex(markerIndex, visiblePoints.length);
              const y = yForValue(markerValue, yMin, yMax, PAD_TOP, priceBottom);
              const distributionMarker = isDistributionMarker(marker);
              return (
                <g key={marker.key}>
                  <line
                    opacity={distributionMarker ? "0.5" : "0.55"}
                    stroke={marker.color}
                    strokeDasharray={distributionMarker ? "4 6" : "3 7"}
                    strokeWidth={distributionMarker ? "1.3" : "1.5"}
                    vectorEffect="non-scaling-stroke"
                    x1={x}
                    x2={x}
                    y1={PAD_TOP}
                    y2={priceBottom}
                  />
                  {!distributionMarker && (
                    <>
                      <circle cx={x} cy={y} fill={marker.color} r="4" vectorEffect="non-scaling-stroke" />
                      <text fill={marker.color} fontSize="11" fontWeight="700" textAnchor="middle" x={x} y={Math.max(18, y - 10)}>
                        {truncateLabel(marker.label)}
                      </text>
                    </>
                  )}
                </g>
              );
            })}
            {dateTickMode === "weekly" && (
              <g>
                {visiblePoints.map((point, index) => {
                  const x = xForIndex(index, visiblePoints.length);
                  const monday = isMonday(point.date);
                  return (
                    <g key={`${point.date}-x-tick`}>
                      <line
                        stroke="#aab2c0"
                        strokeWidth={monday ? "1.2" : "0.8"}
                        x1={x}
                        x2={x}
                        y1={HEIGHT - PAD_BOTTOM + 4}
                        y2={HEIGHT - PAD_BOTTOM + (monday ? 14 : 9)}
                      />
                      {monday && (
                        <text fill="#4a5362" fontSize="10" textAnchor="middle" x={x} y={HEIGHT - 14}>
                          {formatShortDate(point.date)}
                        </text>
                      )}
                    </g>
                  );
                })}
              </g>
            )}
            {hasSubChart && (
              <g>
                <line stroke="#d9dee8" strokeWidth="1" x1={PAD_X} x2={WIDTH - PAD_X} y1={subTop} y2={subTop} />
                {subTitle && (
                  <text fill="#4a5362" fontSize="11" fontWeight="700" x={PAD_X} y={subTop + 14}>
                    {subTitle}
                  </text>
                )}
                {visibleSubSeries.map((item) => {
                  const path = buildPath(visiblePoints, item.key, subYMin, subYMax, subTop + 18, HEIGHT - PAD_BOTTOM);
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
            {dateTickMode === "ends" && (
              <>
                <text fill="#4a5362" fontSize="12" x={PAD_X} y={HEIGHT - 16}>
                  {visiblePoints[0]?.date}
                </text>
                <text fill="#4a5362" fontSize="12" textAnchor="end" x={WIDTH - PAD_X} y={HEIGHT - 16}>
                  {latest?.date}
                </text>
              </>
            )}
          </svg>
        )}
      </div>

      {toggleSeries.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {toggleSeries.map((item) => {
            const hidden = Boolean(hiddenSeries[item.key]);
            return (
              <button
                className={[
                  "inline-flex items-center gap-2 rounded border px-2.5 py-1.5 text-xs transition",
                  hidden
                    ? "border-[#d8e1ea] bg-[#f9fbfd] text-[#687386] hover:border-[#b8c4d2]"
                    : "border-[#d9dee8] bg-white text-[#172033] shadow-sm hover:border-[#0f766e]"
                ].join(" ")}
                key={`${item.panel}-${item.key}`}
                type="button"
                onClick={() => toggleLine(item.key)}
              >
                {hidden ? <EyeOff size={13} /> : <Eye size={13} />}
                <span className="size-2 rounded-full" style={{ backgroundColor: item.color }} />
                {item.label}
              </button>
            );
          })}
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-3">
        {volumeKey && (
          <div className="flex items-center gap-2 text-sm text-[#172033]">
            <span className="size-2 rounded-full bg-[#697386]" />
            <span className="text-[#687386]">{volumeLabel}</span>
            <span className="tabular-nums">{formatCompact(toNumber(latest?.[volumeKey]))}</span>
          </div>
        )}
        {visibleSeries.map((item) => {
          const value = latest ? toNumber(latest[item.key]) : null;
          return (
            <div key={item.key} className="flex items-center gap-2 text-sm text-[#172033]">
              <span className="size-2 rounded-full" style={{ backgroundColor: item.color }} />
              <span className="text-[#687386]">{item.label}</span>
              <span className="tabular-nums">{value === null ? "-" : (item.formatter?.(value) ?? value.toFixed(2))}</span>
            </div>
          );
        })}
        {visibleSubSeries.map((item) => {
          const value = latest ? toNumber(latest[item.key]) : null;
          return (
            <div key={item.key} className="flex items-center gap-2 text-sm text-[#172033]">
              <span className="size-2 rounded-full" style={{ backgroundColor: item.color }} />
              <span className="text-[#687386]">{item.label}</span>
              <span className="tabular-nums">{value === null ? "-" : (item.formatter?.(value) ?? value.toFixed(2))}</span>
            </div>
          );
        })}
        {levels.map((level) => (
          <div key={level.key} className="flex items-center gap-2 text-sm text-[#172033]">
            <span className="h-px w-4 border-t border-dashed" style={{ borderColor: level.color }} />
            <span className="text-[#687386]">{level.label}</span>
            <span className="tabular-nums">{level.value.toFixed(2)}</span>
          </div>
        ))}
        {hasDistributionMarkers && (
          <div className="flex items-center gap-2 text-sm text-[#172033]">
            <span className="h-4 border-l border-dashed border-[#111827]" />
            <span className="text-[#687386]">Distributionstag</span>
          </div>
        )}
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

function clampVisibleRange(range: Pick<VisibleRange, "start" | "end">, total: number) {
  if (total <= 0) return { start: 0, end: 0, total };
  const minWindow = Math.min(MIN_VISIBLE_POINTS, total);
  let start = Math.max(0, Math.min(total - 1, Math.floor(range.start)));
  let end = Math.max(0, Math.min(total - 1, Math.floor(range.end)));
  if (end < start) {
    [start, end] = [end, start];
  }

  if (end - start + 1 < minWindow) {
    end = start + minWindow - 1;
    if (end >= total) {
      end = total - 1;
      start = Math.max(0, end - minWindow + 1);
    }
  }
  return { start, end, total };
}

function fullVisibleRange(total: number): VisibleRange {
  return { start: 0, end: Math.max(0, total - 1), total };
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

function isDistributionMarker(marker: ChartMarker) {
  return marker.key.startsWith("dist-") || marker.label.toLowerCase().includes("distribution");
}

function toNumber(value: string | number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return value;
}

function truncateLabel(label: string) {
  return label.length > 18 ? `${label.slice(0, 17)}...` : label;
}

function isMonday(date: string) {
  const parsed = new Date(`${date}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.getUTCDay() === 1;
}

function formatShortDate(date: string) {
  const parsed = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return date;
  return new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit" }).format(parsed);
}

function formatCompact(value: number | null) {
  if (value === null) return "-";
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)} Mrd.`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} Mio.`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} Tsd.`;
  return value.toFixed(0);
}
