"use client";

import { Eye, EyeOff, Maximize2, Minimize2, Minus, Plus, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, ReactNode } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { formatNumber, formatPercent } from "@/lib/format";

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
  code?: string;
  legendLabel?: string;
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

const DEFAULT_WIDTH = 1000;
const HEIGHT = 400;
const PLOT_LEFT = 18;
const PAD_TOP = 38;
const TIME_AXIS_Y = 370;
const MIN_VISIBLE_POINTS = 20;
const UP_COLOR = "#059669";
const DOWN_COLOR = "#dc2626";

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

type HoverState = {
  index: number;
  price: number;
  y: number;
};

type PriceScale = {
  min: number;
  max: number;
  ticks: number[];
};

type TimeTick = {
  index: number;
  label: string;
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
  const cardRef = useRef<HTMLElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const [visibleRange, setVisibleRange] = useState<VisibleRange>(() => fullVisibleRange(points.length));
  const [hiddenSeries, setHiddenSeries] = useState<Record<string, boolean>>({});
  const [hover, setHover] = useState<HoverState | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [chartSize, setChartSize] = useState({ width: 0, height: 0 });
  const canvasWidth = chartSize.width > 0 && chartSize.height > 0
    ? Math.max(360, (chartSize.width / chartSize.height) * HEIGHT)
    : DEFAULT_WIDTH;
  const priceAxisWidth = levels.length > 0 ? (chartSize.width < 640 ? 136 : 154) : 96;
  const plotRight = canvasWidth - priceAxisWidth;

  const normalizedRange = useMemo(
    () => visibleRange.total === points.length
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
  const hasVolume = Boolean(volumeKey);
  const subBottom = TIME_AXIS_Y - 12;
  const subTop = hasSubChart ? subBottom - 58 : subBottom;
  const volumeBottom = hasSubChart ? subTop - 10 : subBottom;
  const volumeTop = hasVolume ? volumeBottom - 58 : volumeBottom;
  const priceBottom = hasVolume ? volumeTop - 10 : hasSubChart ? subTop - 10 : subBottom;

  const numericValues = visiblePoints.flatMap((point) =>
    visibleSeries
      .map((item) => toNumber(point[item.key]))
      .filter((value): value is number => value !== null)
  );
  const candleValues = chartMode === "candlestick"
    ? visiblePoints.flatMap((point) =>
        ["open", "high", "low", "close"]
          .map((key) => toNumber(point[key]))
          .filter((value): value is number => value !== null)
      )
    : [];
  const levelValues = levels.map((level) => level.value).filter((value) => Number.isFinite(value));
  const priceScale = createPriceScale([...numericValues, ...candleValues, ...levelValues], chartSize.width < 640 ? 5 : 7);

  const subValues = visiblePoints.flatMap((point) =>
    visibleSubSeries
      .map((item) => toNumber(point[item.key]))
      .filter((value): value is number => value !== null)
  );
  const subScale = createPaddedRange(subValues);
  const volumeValues = volumeKey
    ? visiblePoints.map((point) => toNumber(point[volumeKey])).filter((value): value is number => value !== null)
    : [];
  const maxVolume = volumeValues.length ? Math.max(...volumeValues) : 0;
  const latestVisible = visiblePoints.at(-1);
  const latestPoint = points.at(-1);
  const latestClose = chartMode === "candlestick" ? toNumber(latestPoint?.close) : null;
  const latestIsVisible = normalizedRange.end === points.length - 1;
  const latestUp = (toNumber(latestPoint?.close) ?? 0) >= (toNumber(latestPoint?.open) ?? 0);
  const currentPriceColor = latestUp ? UP_COLOR : DOWN_COLOR;
  const hasError = Boolean(error);
  const empty = !isLoading && (!visiblePoints.length || (!numericValues.length && !candleValues.length && !subValues.length));
  const currentWindow = normalizedRange.end - normalizedRange.start + 1;
  const minWindow = Math.min(MIN_VISIBLE_POINTS, points.length);
  const canZoomIn = points.length > 1 && currentWindow > minWindow;
  const canZoomOut = points.length > 1 && currentWindow < points.length;
  const timeTicks = useMemo(
    () => createTimeTicks(visiblePoints, chartSize.width, dateTickMode),
    [chartSize.width, dateTickMode, visiblePoints]
  );
  const visibleMarkers = useMemo(() => layoutMarkers(markers, visiblePoints, plotRight), [markers, plotRight, visiblePoints]);
  const levelLayouts = layoutLevelLabels(levels, priceScale, priceBottom);
  const eventLegend = useMemo(() => createEventLegend(markers), [markers]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const updateSize = () => {
      const rect = chart.getBoundingClientRect();
      setChartSize({ width: rect.width, height: rect.height });
    };
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(chart);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || points.length <= 1) return;

    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = chart.getBoundingClientRect();
      if (!rect.width) return;
      const current = clampVisibleRange(normalizedRange, points.length);
      const windowSize = current.end - current.start + 1;
      const nextWindow = Math.max(
        Math.min(MIN_VISIBLE_POINTS, points.length),
        Math.min(points.length, Math.round(windowSize * (event.deltaY > 0 ? 1.16 : 0.84)))
      );
      const plotLeft = rect.left + (PLOT_LEFT / canvasWidth) * rect.width;
      const plotWidth = ((plotRight - PLOT_LEFT) / canvasWidth) * rect.width;
      const cursorRatio = Math.max(0, Math.min(1, (event.clientX - plotLeft) / plotWidth));
      const anchor = current.start + cursorRatio * Math.max(1, windowSize - 1);
      const nextStart = Math.round(anchor - cursorRatio * Math.max(1, nextWindow - 1));
      setHover(null);
      setVisibleRange(clampVisibleRange({ start: nextStart, end: nextStart + nextWindow - 1 }, points.length));
    };

    chart.addEventListener("wheel", handleWheel, { passive: false });
    return () => chart.removeEventListener("wheel", handleWheel);
  }, [canvasWidth, normalizedRange, plotRight, points.length]);

  useEffect(() => {
    const handleFullscreenChange = () => setIsFullscreen(document.fullscreenElement === cardRef.current);
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  function zoomBy(factor: number) {
    if (points.length <= 1) return;
    const current = clampVisibleRange(normalizedRange, points.length);
    const windowSize = current.end - current.start + 1;
    const nextWindow = Math.max(minWindow, Math.min(points.length, Math.round(windowSize * factor)));
    const center = current.start + Math.max(1, windowSize - 1) / 2;
    const nextStart = Math.round(center - Math.max(1, nextWindow - 1) / 2);
    setHover(null);
    setVisibleRange(clampVisibleRange({ start: nextStart, end: nextStart + nextWindow - 1 }, points.length));
  }

  function resetZoom() {
    setHover(null);
    setVisibleRange(fullVisibleRange(points.length));
  }

  function toggleLine(key: string) {
    setHiddenSeries((current) => ({ ...current, [key]: !current[key] }));
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (points.length <= MIN_VISIBLE_POINTS) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { pointerId: event.pointerId, clientX: event.clientX, range: normalizedRange };
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const rect = chartRef.current?.getBoundingClientRect();
    if (!rect?.width || !rect.height) return;
    const index = indexAtClientX(event.clientX, rect, visiblePoints.length, canvasWidth, plotRight);
    const svgY = ((event.clientY - rect.top) / rect.height) * HEIGHT;
    const y = Math.max(PAD_TOP, Math.min(priceBottom, svgY));
    setHover({
      index,
      price: valueForY(y, priceScale.min, priceScale.max, PAD_TOP, priceBottom),
      y
    });

    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const plotWidth = ((plotRight - PLOT_LEFT) / canvasWidth) * rect.width;
    const windowSize = drag.range.end - drag.range.start + 1;
    const pointsPerPixel = windowSize / Math.max(1, plotWidth);
    const offset = Math.round((drag.clientX - event.clientX) * pointsPerPixel);
    setVisibleRange(clampVisibleRange({ start: drag.range.start + offset, end: drag.range.end + offset }, points.length));
  }

  function handlePointerEnd(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement === cardRef.current) {
        await document.exitFullscreen();
        return;
      }
      await cardRef.current?.requestFullscreen();
    } catch {
      // Some embedded browsers deny fullscreen; the chart remains fully usable inline.
      return;
    }
  }

  const hoveredPoint = hover ? visiblePoints[hover.index] : null;
  const hoveredX = hover ? xForIndex(hover.index, visiblePoints.length, plotRight) : null;
  const activePoint = hoveredPoint ?? latestVisible;

  return (
    <section
      ref={cardRef}
      className={isFullscreen
        ? "flex h-screen w-screen flex-col overflow-hidden bg-[var(--background)] p-4"
        : "rounded-[var(--radius-panel)] border border-[var(--border)] bg-[var(--panel)] p-3 shadow-[var(--shadow-card)] sm:p-4"}
    >
      <div className={hideTextHeader ? "mb-2 flex justify-end" : "mb-3 flex flex-col gap-2 md:flex-row md:items-start md:justify-between"}>
        {!hideTextHeader && (
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-[var(--text)]">{title}</h2>
            <p className="mt-0.5 text-sm leading-5 text-[var(--muted)]">{caption}</p>
          </div>
        )}
        <div className="flex shrink-0 items-center gap-2">
          <div className="inline-flex overflow-hidden rounded-md border border-[var(--border)] bg-[var(--panel-soft)] shadow-sm">
            <ChartToolButton disabled={!canZoomIn} label="In den Chart hineinzoomen" onClick={() => zoomBy(0.72)}><Plus size={13} /></ChartToolButton>
            <ChartToolButton disabled={!canZoomOut} label="Aus dem Chart herauszoomen" onClick={() => zoomBy(1.38)}><Minus size={13} /></ChartToolButton>
            <ChartToolButton disabled={!isZoomed} label="Chart zurücksetzen" onClick={resetZoom}><RotateCcw size={13} /></ChartToolButton>
            <ChartToolButton label={isFullscreen ? "Vollbild schließen" : "Chart im Vollbild öffnen"} onClick={toggleFullscreen}>
              {isFullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            </ChartToolButton>
          </div>
          {!hideTextHeader && statusLabel && <StatusChip tone={statusTone}>{statusLabel}</StatusChip>}
        </div>
      </div>

      <div
        ref={chartRef}
        className={[
          "relative touch-none select-none overflow-hidden rounded-[10px] border border-[var(--border)] bg-[var(--panel)]",
          isFullscreen ? "min-h-0 flex-1" : "h-[430px] sm:h-[470px]",
          isZoomed ? "cursor-grab active:cursor-grabbing" : "cursor-crosshair"
        ].join(" ")}
        onPointerCancel={handlePointerEnd}
        onPointerDown={handlePointerDown}
        onPointerLeave={(event) => {
          setHover(null);
          handlePointerEnd(event);
        }}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onDoubleClick={resetZoom}
      >
        {!isLoading && !hasError && !empty && activePoint && (
          <ChartHoverReadout chartMode={chartMode} point={activePoint} series={visibleSeries} volumeKey={volumeKey} isHovered={Boolean(hoveredPoint)} isLatest={activePoint === latestPoint} />
        )}
        {isLoading && <ChartMessage>Daten werden geladen...</ChartMessage>}
        {hasError && <ChartMessage tone="error">Chart-Daten konnten nicht geladen werden.</ChartMessage>}
        {empty && !hasError && <ChartMessage>Keine Zeitreihe verfügbar.</ChartMessage>}

        {!isLoading && !hasError && !empty && (
          <svg className="size-full" preserveAspectRatio="none" role="img" viewBox={`0 0 ${canvasWidth} ${HEIGHT}`}>
            <title>{`${title}: interaktiver Chart. Mausrad zoomt, Ziehen verschiebt, Doppelklick setzt zurück.`}</title>
            <rect fill="var(--panel)" height={HEIGHT} width={canvasWidth} />

            {showHorizontalGrid && priceScale.ticks.map((tick) => {
              const y = yForValue(tick, priceScale.min, priceScale.max, PAD_TOP, priceBottom);
              return <line key={`price-grid-${tick}`} stroke="var(--border)" strokeWidth="0.8" vectorEffect="non-scaling-stroke" x1={PLOT_LEFT} x2={plotRight} y1={y} y2={y} />;
            })}
            {timeTicks.map((tick) => {
              const x = xForIndex(tick.index, visiblePoints.length, plotRight);
              return <line key={`time-grid-${tick.index}`} opacity="0.65" stroke="var(--border)" strokeWidth="0.8" vectorEffect="non-scaling-stroke" x1={x} x2={x} y1={PAD_TOP} y2={TIME_AXIS_Y} />;
            })}

            {hasVolume && maxVolume > 0 && volumeKey && (
              <g>
                <rect fill="var(--panel-soft)" height={volumeBottom - volumeTop} width={plotRight - PLOT_LEFT} x={PLOT_LEFT} y={volumeTop} />
                <line stroke="var(--border)" strokeWidth="0.8" x1={PLOT_LEFT} x2={plotRight} y1={volumeTop} y2={volumeTop} />
                <text fill="var(--muted)" fontSize="10" fontWeight="600" x={PLOT_LEFT + 6} y={volumeTop + 12}>
                  {volumeLabel} · {formatCompact(toNumber(activePoint?.[volumeKey]))}
                </text>
                {visiblePoints.map((point, index) => {
                  const volume = toNumber(point[volumeKey]);
                  if (volume === null) return null;
                  const maxBarHeight = volumeBottom - volumeTop - 17;
                  const barHeight = Math.max(1, (volume / maxVolume) * maxBarHeight);
                  const barWidth = Math.max(1.5, ((plotRight - PLOT_LEFT) / Math.max(1, visiblePoints.length)) * 0.68);
                  const x = xForIndex(index, visiblePoints.length, plotRight) - barWidth / 2;
                  const close = toNumber(point.close);
                  const open = toNumber(point.open);
                  const fill = close !== null && open !== null && close < open ? DOWN_COLOR : UP_COLOR;
                  return <rect key={`${point.date}-${index}-volume`} fill={fill} height={barHeight} opacity="0.36" width={barWidth} x={x} y={volumeBottom - barHeight} />;
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
                  const x = xForIndex(index, visiblePoints.length, plotRight);
                  const candleWidth = Math.min(13, Math.max(2, ((plotRight - PLOT_LEFT) / Math.max(1, visiblePoints.length)) * 0.7));
                  const yHigh = yForValue(high, priceScale.min, priceScale.max, PAD_TOP, priceBottom);
                  const yLow = yForValue(low, priceScale.min, priceScale.max, PAD_TOP, priceBottom);
                  const yOpen = yForValue(open, priceScale.min, priceScale.max, PAD_TOP, priceBottom);
                  const yClose = yForValue(close, priceScale.min, priceScale.max, PAD_TOP, priceBottom);
                  const color = close >= open ? UP_COLOR : DOWN_COLOR;
                  return (
                    <g key={`${point.date}-candle`} opacity={hover && hover.index !== index ? "0.82" : "1"}>
                      <line stroke={color} strokeWidth="1" vectorEffect="non-scaling-stroke" x1={x} x2={x} y1={yHigh} y2={yLow} />
                      <rect fill={color} height={Math.max(1.4, Math.abs(yClose - yOpen))} stroke={color} strokeWidth="0.8" vectorEffect="non-scaling-stroke" width={candleWidth} x={x - candleWidth / 2} y={Math.min(yOpen, yClose)} />
                    </g>
                  );
                })}
              </g>
            )}

            {visibleSeries.map((item) => {
              const path = buildPath(visiblePoints, item.key, priceScale.min, priceScale.max, PAD_TOP, priceBottom, plotRight);
              if (!path) return null;
              return <path key={item.key} d={path} fill="none" stroke={item.color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.35" vectorEffect="non-scaling-stroke" />;
            })}

            {levelLayouts.map(({ level, lineY, labelY }) => (
              <g key={level.key}>
                <line opacity="0.78" stroke={level.color} strokeDasharray="6 5" strokeWidth="1" vectorEffect="non-scaling-stroke" x1={PLOT_LEFT} x2={plotRight} y1={lineY} y2={lineY} />
                {Math.abs(lineY - labelY) > 1 && <line stroke={level.color} strokeWidth="0.8" x1={plotRight} x2={plotRight + 5} y1={lineY} y2={labelY} />}
                <rect fill="var(--panel)" height="18" rx="3" stroke={level.color} strokeWidth="0.8" vectorEffect="non-scaling-stroke" width={canvasWidth - plotRight - 8} x={plotRight + 4} y={labelY - 9} />
                <text fill={level.color} fontSize="10.5" fontWeight="700" x={plotRight + 9} y={labelY + 3.5}>{compactLevelLabel(level.label)} {formatPrice(level.value)}</text>
              </g>
            ))}

            {latestIsVisible && latestClose !== null && (
              <g pointerEvents="none">
                <line opacity="0.72" stroke={currentPriceColor} strokeDasharray="2 3" strokeWidth="1" vectorEffect="non-scaling-stroke" x1={PLOT_LEFT} x2={plotRight} y1={yForValue(latestClose, priceScale.min, priceScale.max, PAD_TOP, priceBottom)} y2={yForValue(latestClose, priceScale.min, priceScale.max, PAD_TOP, priceBottom)} />
                <AxisLabel canvasWidth={canvasWidth} color={currentPriceColor} plotRight={plotRight} text={formatPrice(latestClose)} y={yForValue(latestClose, priceScale.min, priceScale.max, PAD_TOP, priceBottom)} />
              </g>
            )}

            {hasSubChart && (
              <g>
                <rect fill="var(--panel-soft)" height={subBottom - subTop} width={plotRight - PLOT_LEFT} x={PLOT_LEFT} y={subTop} />
                <line stroke="var(--border)" strokeWidth="0.8" x1={PLOT_LEFT} x2={plotRight} y1={subTop} y2={subTop} />
                {subTitle && <text fill="var(--muted)" fontSize="10" fontWeight="600" x={PLOT_LEFT + 6} y={subTop + 12}>{subTitle}</text>}
                {visibleSubSeries.map((item) => {
                  const path = buildPath(visiblePoints, item.key, subScale.min, subScale.max, subTop + 16, subBottom, plotRight);
                  if (!path) return null;
                  return <path key={item.key} d={path} fill="none" stroke={item.color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />;
                })}
              </g>
            )}

            <line stroke="var(--border-strong)" strokeWidth="0.8" x1={plotRight} x2={plotRight} y1={PAD_TOP} y2={TIME_AXIS_Y} />
            {priceScale.ticks.map((tick) => {
              const y = yForValue(tick, priceScale.min, priceScale.max, PAD_TOP, priceBottom);
              const overlapsMarker = levelLayouts.some((layout) => Math.abs(layout.labelY - y) < 12)
                || (latestIsVisible && latestClose !== null && Math.abs(yForValue(latestClose, priceScale.min, priceScale.max, PAD_TOP, priceBottom) - y) < 12);
              return (
                <g key={`price-tick-${tick}`}>
                  <line stroke="var(--border-strong)" strokeWidth="0.8" x1={plotRight} x2={plotRight + 5} y1={y} y2={y} />
                  {!overlapsMarker && <text fill="var(--muted)" fontSize="10.5" style={{ fontVariantNumeric: "tabular-nums" }} x={plotRight + 9} y={y + 3.5}>{formatPrice(tick)}</text>}
                </g>
              );
            })}
            <line stroke="var(--border-strong)" strokeWidth="0.8" x1={PLOT_LEFT} x2={plotRight} y1={TIME_AXIS_Y} y2={TIME_AXIS_Y} />
            {timeTicks.map((tick) => {
              const x = xForIndex(tick.index, visiblePoints.length, plotRight);
              return (
                <g key={`time-tick-${tick.index}`}>
                  <line stroke="var(--border-strong)" strokeWidth="0.8" x1={x} x2={x} y1={TIME_AXIS_Y} y2={TIME_AXIS_Y + 4} />
                  <text fill="var(--muted)" fontSize="10" textAnchor="middle" x={x} y={TIME_AXIS_Y + 16}>{tick.label}</text>
                </g>
              );
            })}

            {visibleMarkers.map(({ marker, index, track }) => {
              const x = xForIndex(index, visiblePoints.length, plotRight);
              const markerY = TIME_AXIS_Y - 12 - track * 17;
              const code = eventCode(marker);
              return (
                <g key={marker.key}>
                  <title>{`${marker.label} · ${formatLongDate(marker.date)}`}</title>
                  <line opacity="0.32" stroke={marker.color} strokeDasharray="3 5" strokeWidth="1" vectorEffect="non-scaling-stroke" x1={x} x2={x} y1={PAD_TOP} y2={markerY - 7} />
                  <rect fill="var(--panel)" height="14" rx="3" stroke={marker.color} strokeWidth="0.9" width={eventCodeWidth(code)} x={x - eventCodeWidth(code) / 2} y={markerY - 7} />
                  <text fill={marker.color} fontSize="9" fontWeight="800" textAnchor="middle" x={x} y={markerY + 3}>{code}</text>
                </g>
              );
            })}

            {hoveredX !== null && hoveredPoint && hover && (
              <g pointerEvents="none">
                <line opacity="0.72" stroke="var(--muted)" strokeDasharray="3 4" strokeWidth="0.85" vectorEffect="non-scaling-stroke" x1={hoveredX} x2={hoveredX} y1={PAD_TOP} y2={TIME_AXIS_Y} />
                <line opacity="0.72" stroke="var(--muted)" strokeDasharray="3 4" strokeWidth="0.85" vectorEffect="non-scaling-stroke" x1={PLOT_LEFT} x2={plotRight} y1={hover.y} y2={hover.y} />
                <AxisLabel canvasWidth={canvasWidth} color="var(--text)" plotRight={plotRight} text={formatPrice(hover.price)} y={hover.y} />
                <rect fill="var(--text)" height="18" rx="3" width="72" x={Math.max(PLOT_LEFT, Math.min(plotRight - 72, hoveredX - 36))} y={TIME_AXIS_Y - 9} />
                <text fill="var(--panel)" fontSize="9.5" fontWeight="600" textAnchor="middle" x={Math.max(PLOT_LEFT + 36, Math.min(plotRight - 36, hoveredX))} y={TIME_AXIS_Y + 3.5}>{formatCrosshairDate(hoveredPoint.date)}</text>
              </g>
            )}
          </svg>
        )}
      </div>

      {(toggleSeries.length > 0 || eventLegend.length > 0) && (
        <div className="mt-2 flex flex-wrap items-center gap-x-1 gap-y-1 text-[11px]">
          {toggleSeries.map((item) => {
            const hidden = Boolean(hiddenSeries[item.key]);
            const value = latestPoint ? toNumber(latestPoint[item.key]) : null;
            return (
              <button
                className={["inline-flex h-6 items-center gap-1.5 rounded px-1.5 tabular-nums transition", hidden ? "text-[var(--muted-soft)] hover:bg-[var(--panel-soft)]" : "text-[var(--text)] hover:bg-[var(--panel-soft)]"].join(" ")}
                key={`${item.panel}-${item.key}`}
                title={`${hidden ? "Einblenden" : "Ausblenden"}: ${item.label}`}
                type="button"
                onClick={() => toggleLine(item.key)}
              >
                {hidden ? <EyeOff size={11} /> : <Eye size={11} />}
                <span className="size-1.5 rounded-full" style={{ backgroundColor: item.color }} />
                <span className="font-semibold">{compactSeriesLabel(item.label)}</span>
                {!hidden && <span className="text-[var(--muted)]">{value === null ? "–" : (item.formatter?.(value) ?? formatNumber(value, 2))}</span>}
              </button>
            );
          })}
          {eventLegend.map((entry) => (
            <span className="inline-flex h-6 items-center gap-1.5 px-1.5 text-[var(--muted)]" key={`${entry.code}-${entry.label}`}>
              <span className="rounded border px-1 text-[9px] font-bold" style={{ borderColor: entry.color, color: entry.color }}>{entry.code}</span>
              {entry.label}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function ChartToolButton({ children, disabled, label, onClick }: { children: ReactNode; disabled?: boolean; label: string; onClick: () => void }) {
  return (
    <button aria-label={label} className="inline-flex size-7 items-center justify-center border-r border-[var(--border)] text-[var(--muted)] transition last:border-r-0 hover:bg-[var(--panel)] hover:text-[var(--teal)] disabled:cursor-not-allowed disabled:opacity-35" disabled={disabled} title={label} type="button" onClick={onClick}>
      {children}
    </button>
  );
}

function ChartMessage({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "error" }) {
  return <div className={`absolute inset-0 grid place-items-center px-4 text-center text-sm ${tone === "error" ? "font-medium text-[var(--red)]" : "text-[var(--muted)]"}`}>{children}</div>;
}

function AxisLabel({ canvasWidth, color, plotRight, text, y }: { canvasWidth: number; color: string; plotRight: number; text: string; y: number }) {
  return (
    <g>
      <rect fill={color} height="18" rx="3" width={canvasWidth - plotRight - 8} x={plotRight + 4} y={y - 9} />
      <text fill="white" fontSize="10.5" fontWeight="700" x={plotRight + 9} y={y + 3.5}>{text}</text>
    </g>
  );
}

function ChartHoverReadout({ chartMode, point, series, volumeKey, isHovered, isLatest }: { chartMode: "line" | "candlestick"; point: ChartDatum; series: ChartSeries[]; volumeKey?: string; isHovered: boolean; isLatest: boolean }) {
  const open = toNumber(point.open);
  const high = toNumber(point.high);
  const low = toNumber(point.low);
  const close = toNumber(point.close);
  const dayChange = open !== null && open !== 0 && close !== null ? ((close - open) / open) * 100 : null;
  const volume = volumeKey ? toNumber(point[volumeKey]) : null;

  return (
    <div className="pointer-events-none absolute left-2 top-2 z-10 max-w-[calc(100%-8rem)] rounded-md border border-[var(--border)] bg-white/94 px-2.5 py-1.5 shadow-sm backdrop-blur sm:left-3 sm:top-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] tabular-nums sm:text-[11px]">
        <span className="font-semibold text-[var(--text)]">{formatLongDate(point.date)}</span>
        {chartMode === "candlestick" && (
          <>
            <HoverValue label="O" value={open} /><HoverValue label="H" value={high} /><HoverValue label="T" value={low} /><HoverValue label="S" value={close} />
            {dayChange !== null && <span className={dayChange >= 0 ? "font-semibold text-[var(--green)]" : "font-semibold text-[var(--red)]"}>{formatPercent(dayChange, 2)}</span>}
            {volume !== null && <span className="text-[var(--muted)]">Vol. <span className="font-semibold text-[var(--text)]">{formatCompact(volume)}</span></span>}
          </>
        )}
        {chartMode === "line" && series.map((item) => {
          const value = toNumber(point[item.key]);
          if (value === null) return null;
          return <span key={item.key} className="text-[var(--muted)]">{item.label} <span className="font-semibold text-[var(--text)]">{item.formatter?.(value) ?? formatNumber(value, 2)}</span></span>;
        })}
        {!isHovered && <span className="text-[var(--muted-soft)]">{isLatest ? "Letzter Handelstag" : "Letzter sichtbarer Tag"}</span>}
      </div>
    </div>
  );
}

function HoverValue({ label, value }: { label: string; value: number | null }) {
  if (value === null) return null;
  return <span className="text-[var(--muted)]">{label} <span className="font-semibold text-[var(--text)]">{formatPrice(value)}</span></span>;
}

function buildPath(points: ChartDatum[], key: string, yMin: number, yMax: number, top: number, bottom: number, plotRight: number) {
  const segments: string[] = [];
  let drawing = false;
  points.forEach((point, index) => {
    const value = toNumber(point[key]);
    if (value === null) {
      drawing = false;
      return;
    }
    const x = xForIndex(index, points.length, plotRight);
    const y = yForValue(value, yMin, yMax, top, bottom);
    segments.push(`${drawing ? "L" : "M"} ${x.toFixed(2)} ${y.toFixed(2)}`);
    drawing = true;
  });
  return segments.length > 1 ? segments.join(" ") : "";
}

function xForIndex(index: number, total: number, plotRight: number) {
  if (total <= 1) return PLOT_LEFT;
  return PLOT_LEFT + (index / (total - 1)) * (plotRight - PLOT_LEFT);
}

function indexAtClientX(clientX: number, rect: DOMRect, total: number, canvasWidth: number, plotRight: number) {
  if (total <= 1) return 0;
  const plotLeft = rect.left + (PLOT_LEFT / canvasWidth) * rect.width;
  const plotWidth = ((plotRight - PLOT_LEFT) / canvasWidth) * rect.width;
  const ratio = Math.max(0, Math.min(1, (clientX - plotLeft) / plotWidth));
  return Math.round(ratio * (total - 1));
}

function clampVisibleRange(range: Pick<VisibleRange, "start" | "end">, total: number): VisibleRange {
  if (total <= 0) return { start: 0, end: 0, total };
  const minWindow = Math.min(MIN_VISIBLE_POINTS, total);
  let start = Math.max(0, Math.min(total - 1, Math.floor(range.start)));
  let end = Math.max(0, Math.min(total - 1, Math.floor(range.end)));
  if (end < start) [start, end] = [end, start];
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
  const ratio = (value - yMin) / (yMax - yMin || 1);
  return top + (1 - ratio) * (bottom - top);
}

function valueForY(y: number, yMin: number, yMax: number, top: number, bottom: number) {
  const ratio = (y - top) / (bottom - top || 1);
  return yMax - ratio * (yMax - yMin);
}

function toNumber(value: string | number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function createPaddedRange(values: number[]) {
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;
  const span = max - min || Math.max(1, Math.abs(max) * 0.04);
  return { min: min - span * 0.08, max: max + span * 0.08 };
}

export function createPriceScale(values: number[], targetTickCount = 7): PriceScale {
  const finite = values.filter(Number.isFinite);
  if (!finite.length) return { min: 0, max: 1, ticks: [0, 0.2, 0.4, 0.6, 0.8, 1] };
  const rawMin = Math.min(...finite);
  const rawMax = Math.max(...finite);
  const baseSpan = rawMax - rawMin || Math.max(Math.abs(rawMax) * 0.04, 0.01);
  const paddedMin = rawMin - baseSpan * 0.06;
  const paddedMax = rawMax + baseSpan * 0.06;
  let step = niceStep((paddedMax - paddedMin) / Math.max(2, targetTickCount - 1));
  let min = Math.floor(paddedMin / step) * step;
  let max = Math.ceil(paddedMax / step) * step;
  let ticks = ticksBetween(min, max, step);
  if (ticks.length > 8) {
    step = niceStep(step * 1.6);
    min = Math.floor(paddedMin / step) * step;
    max = Math.ceil(paddedMax / step) * step;
    ticks = ticksBetween(min, max, step);
  }
  return { min, max, ticks };
}

function niceStep(value: number) {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const exponent = Math.floor(Math.log10(value));
  const fraction = value / 10 ** exponent;
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  return niceFraction * 10 ** exponent;
}

function ticksBetween(min: number, max: number, step: number) {
  const count = Math.min(20, Math.round((max - min) / step) + 1);
  return Array.from({ length: count }, (_, index) => Number((min + index * step).toPrecision(12)));
}

export function createTimeTicks(points: ChartDatum[], containerWidth: number, mode: "ends" | "weekly" = "ends"): TimeTick[] {
  if (!points.length) return [];
  const parsed = points.map((point) => parseDate(point.date));
  const first = parsed[0];
  const last = parsed.at(-1);
  if (!first || !last) return fallbackTimeTicks(points);
  const spanDays = Math.max(1, (last.getTime() - first.getTime()) / 86_400_000);
  const maxTicks = containerWidth > 900 ? 12 : containerWidth > 640 ? 9 : containerWidth > 440 ? 6 : 4;
  let candidates: number[] = [];
  let formatter: (date: Date, index: number) => string;

  if (mode === "weekly" || spanDays <= 45) {
    const step = Math.max(1, Math.ceil(points.length / maxTicks));
    candidates = points.map((_, index) => index).filter((index) => index % step === 0);
    formatter = (date) => new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit" }).format(date);
  } else if (spanDays <= 550) {
    candidates = boundaryIndexes(parsed, (previous, current) => previous.getUTCMonth() !== current.getUTCMonth() || previous.getUTCFullYear() !== current.getUTCFullYear());
    formatter = (date, index) => {
      const month = new Intl.DateTimeFormat("de-DE", { month: "short" }).format(date).replace(".", "");
      return date.getUTCMonth() === 0 || index === 0 ? `${month} ${String(date.getUTCFullYear()).slice(-2)}` : month;
    };
  } else if (spanDays <= 1100) {
    candidates = boundaryIndexes(parsed, (previous, current) => {
      const monthChanged = previous.getUTCMonth() !== current.getUTCMonth() || previous.getUTCFullYear() !== current.getUTCFullYear();
      return monthChanged && current.getUTCMonth() % 3 === 0;
    });
    formatter = (date) => new Intl.DateTimeFormat("de-DE", { month: "short", year: "2-digit" }).format(date).replace(".", "");
  } else {
    candidates = boundaryIndexes(parsed, (previous, current) => previous.getUTCFullYear() !== current.getUTCFullYear());
    formatter = (date) => String(date.getUTCFullYear());
  }

  candidates = downsampleIndexes(candidates, maxTicks);
  return candidates.map((index) => ({ index, label: formatter(parsed[index]!, index) }));
}

function boundaryIndexes(dates: Array<Date | null>, boundary: (previous: Date, current: Date) => boolean) {
  const indexes = [0];
  for (let index = 1; index < dates.length; index += 1) {
    const previous = dates[index - 1];
    const current = dates[index];
    if (previous && current && boundary(previous, current)) indexes.push(index);
  }
  return indexes;
}

function downsampleIndexes(indexes: number[], maxTicks: number) {
  if (indexes.length <= maxTicks) return indexes;
  const step = Math.ceil(indexes.length / maxTicks);
  return indexes.filter((_, index) => index % step === 0);
}

function fallbackTimeTicks(points: ChartDatum[]) {
  if (points.length === 1) return [{ index: 0, label: points[0].date }];
  return [{ index: 0, label: points[0].date }, { index: points.length - 1, label: points.at(-1)?.date ?? "" }];
}

function parseDate(value: string) {
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatPrice(value: number) {
  return formatNumber(value, 2, 2);
}

function formatLongDate(date: string) {
  const parsed = parseDate(date);
  if (!parsed) return date;
  return new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" }).format(parsed);
}

function formatCrosshairDate(date: string) {
  const parsed = parseDate(date);
  if (!parsed) return date;
  return new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "short", year: "2-digit" }).format(parsed).replace(".", "");
}

function formatCompact(value: number | null) {
  if (value === null) return "–";
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000_000) return `${formatNumber(value / 1_000_000_000, 1)} Mrd.`;
  if (absolute >= 1_000_000) return `${formatNumber(value / 1_000_000, 1)} Mio.`;
  if (absolute >= 1_000) return `${formatNumber(value / 1_000, 1)} Tsd.`;
  return formatNumber(value, 0);
}

function compactSeriesLabel(label: string) {
  const match = label.match(/^(\d+)-(EMA|SMA)$/i);
  return match ? `${match[2].toUpperCase()} ${match[1]}` : label;
}

function compactLevelLabel(label: string) {
  return label === "Startschuss-Tief" ? "Startschuss" : label;
}

function layoutLevelLabels(levels: ChartLevel[], scale: PriceScale, priceBottom: number) {
  const layouts = levels
    .filter((level) => Number.isFinite(level.value))
    .map((level) => ({ level, lineY: yForValue(level.value, scale.min, scale.max, PAD_TOP, priceBottom), labelY: yForValue(level.value, scale.min, scale.max, PAD_TOP, priceBottom) }))
    .sort((a, b) => a.labelY - b.labelY);
  const minimumGap = 20;
  layouts.forEach((layout, index) => {
    layout.labelY = Math.max(PAD_TOP + 9, Math.min(priceBottom - 9, layout.labelY));
    if (index > 0) layout.labelY = Math.max(layout.labelY, layouts[index - 1].labelY + minimumGap);
  });
  for (let index = layouts.length - 1; index >= 0; index -= 1) {
    const maxY = index === layouts.length - 1 ? priceBottom - 9 : layouts[index + 1].labelY - minimumGap;
    layouts[index].labelY = Math.min(layouts[index].labelY, maxY);
  }
  return layouts;
}

function layoutMarkers(markers: ChartMarker[], points: ChartDatum[], plotRight: number) {
  const placed: Array<{ marker: ChartMarker; index: number; track: number; x: number }> = [];
  markers.forEach((marker) => {
    const index = indexForDate(points, marker.date);
    if (index < 0) return;
    const x = xForIndex(index, points.length, plotRight);
    let track = 0;
    while (track < 3 && placed.some((item) => item.track === track && Math.abs(item.x - x) < 22)) track += 1;
    placed.push({ marker, index, track: Math.min(track, 2), x });
  });
  return placed;
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
  return bestDistance <= 86_400_000 * 7 ? bestIndex : -1;
}

function eventCode(marker: ChartMarker) {
  if (marker.code) return marker.code.slice(0, 4);
  if (marker.key === "anchor") return "A";
  if (marker.key.startsWith("dist-")) return "D";
  if (marker.key.startsWith("stall-")) return "S";
  if (marker.key === "auto-52w-high") return "H";
  if (marker.key === "auto-ema21-lost") return "E21";
  if (marker.key === "auto-sma50-lost") return "S50";
  if (marker.key === "auto-volume-spike") return "V";
  return "•";
}

function eventLegendLabel(marker: ChartMarker) {
  if (marker.legendLabel) return marker.legendLabel;
  if (marker.key.startsWith("dist-")) return "Distributionstag";
  if (marker.key.startsWith("stall-")) return "Stautag";
  return marker.label;
}

function createEventLegend(markers: ChartMarker[]) {
  const entries = new Map<string, { code: string; label: string; color: string }>();
  markers.forEach((marker) => {
    const code = eventCode(marker);
    const label = eventLegendLabel(marker);
    const key = `${code}-${label}`;
    if (!entries.has(key)) entries.set(key, { code, label, color: marker.color });
  });
  return Array.from(entries.values()).slice(0, 6);
}

function eventCodeWidth(code: string) {
  return Math.max(14, 8 + code.length * 6);
}
