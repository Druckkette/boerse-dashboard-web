import clsx from "clsx";
import { Zap } from "lucide-react";
import { StatusChip } from "@/components/ui/status-chip";
import type { MarketAmpelPowerTrend, Tone } from "@/lib/types/api";

export function powerTrendPresentation(state: MarketAmpelPowerTrend["state"]): { tone: Tone; label: string } {
  return state === "on" ? { tone: "good", label: "⚡ Powertrend aktiv" } :
    state === "under_pressure" ? { tone: "warning", label: "⚡ Powertrend unter Druck" } :
      { tone: "neutral", label: "Powertrend aus" };
}
export function PowerTrendBadge({ powertrend }: { powertrend: Pick<MarketAmpelPowerTrend, "state"> }) {
  const { tone, label } = powerTrendPresentation(powertrend.state);
  return <StatusChip tone={tone}>{label}</StatusChip>;
}
function germanDate(value: string) {
  const [year, month, day] = value.split("-");
  return `${day}.${month}.${year}`;
}
export function powerTrendDescription(powertrend: Pick<MarketAmpelPowerTrend, "state" | "start_date" | "pressure_since">) {
  const start = powertrend.start_date ? germanDate(powertrend.start_date) : null;
  const started = start ? `Powertrend gestartet am ${start}` : "Startdatum nicht verfügbar";
  return powertrend.state === "off" ? "Kein formal laufender Powertrend" :
    powertrend.state === "under_pressure" ? `${started} · ${powertrend.pressure_since ? `unter Druck seit ${germanDate(powertrend.pressure_since)}` : "aktuell unter Druck"}` : started;

}
export function PowerTrendCard({ powertrend }: { powertrend: MarketAmpelPowerTrend }) {
  const { tone, label } = powerTrendPresentation(powertrend.state);
  const description = powerTrendDescription(powertrend);

  return (
    <div className={clsx("mt-4 rounded-2xl border p-4", tileBorder(tone))}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Zap size={17} className={toneText(tone)} />
          <div>
            <div className="text-sm font-semibold text-[#172033]">Powertrend</div>
            <div className="text-xs text-[#687386]">
              {description}
            </div>
          </div>
        </div>
        <StatusChip tone={tone}>{label}</StatusChip>
      </div>
      <p className="mt-3 text-xs text-[#687386]">
        {powertrend.state === "under_pressure"
          ? "Die Werte zeigen die Voraussetzungen für die Rückkehr zum vollen Powertrend. Der formale Powertrend bleibt bestehen, solange die 21-EMA nicht unter die 50-SMA fällt."
          : powertrend.state === "on"
            ? "Die vier Bedingungen waren am Startdatum vollständig erfüllt. Die Werte zeigen den aktuellen Stand; ein kürzerer Zähler beendet den Powertrend nicht."
            : "Powertrend startet, wenn alle vier Kriterien am selben bestätigten Handelstag erfüllt sind."}
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <PowerTrendCheck
          label="Tagestief > 21-EMA"
          value={`${Math.min(powertrend.low_above_21_streak, 10)}/10`}
          passed={powertrend.low_above_21_streak >= 10}
        />
        <PowerTrendCheck
          label="21-EMA > 50-SMA"
          value={`${Math.min(powertrend.ema21_over_50_streak, 5)}/5`}
          passed={powertrend.ema21_over_50_streak >= 5}
        />
        <PowerTrendCheck
          label="50-SMA steigt"
          value={powertrend.sma50_rising_1d ? "Ja" : "Nein"}
          passed={powertrend.sma50_rising_1d}
        />
        <PowerTrendCheck
          label="Tag positiv/neutral"
          value={powertrend.positive_or_flat_day ? "Ja" : "Nein"}
          passed={powertrend.positive_or_flat_day}
        />
      </div>
      <p className="mt-3 text-xs leading-5 text-[#687386]">
        {powertrend.reason ||
          "Powertrend startet erst, wenn alle vier Kriterien gleichzeitig erfüllt sind. Formal endet er bei 21-EMA unter 50-SMA."}
      </p>

    </div>
  );
}

function PowerTrendCheck({ label, passed, value }: { label: string; passed: boolean; value: string }) {
  return (
    <div className="rounded-xl border border-white/70 bg-white/70 px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#687386]">{label}</div>
      <div className={clsx("mt-1 text-sm font-semibold", passed ? "text-[#059669]" : "text-[#64748b]")}>{value}</div>
    </div>
  );
}

function tileBorder(tone: Tone) {
  return tone === "good" ? "border-[#bbf7d0] bg-[#ecfdf5]" : tone === "warning" ? "border-[#fed7aa] bg-[#fffbeb]" : "border-[#e2e8f0] bg-[#f8fafc]";
}
function toneText(tone: Tone) {
  return tone === "good" ? "text-[#059669]" : tone === "warning" ? "text-[#d97706]" : "text-[#64748b]";
}
