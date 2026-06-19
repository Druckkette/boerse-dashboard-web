"use client";

import { useMemo, useState } from "react";
import { CalendarClock, Database, Save } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import type {
  StockFundamentalsAnnualEps,
  StockFundamentalsEpsQuarter,
  StockFundamentalsItem,
  StockFundamentalsUpdate,
  Tone
} from "@/lib/types/api";

type FundamentalsForm = Required<Omit<StockFundamentalsUpdate, "source">> & {
  source: string;
};

const emptyForm: FundamentalsForm = {
  as_of: "",
  source: "manual",
  fiscal_period: "",
  quarterly_eps_growth_pct: null,
  annual_eps_growth_pct: null,
  quarterly_revenue_growth_pct: null,
  annual_revenue_growth_pct: null,
  roe_pct: null,
  profit_margin_pct: null,
  trailing_eps: null,
  quarterly_eps_accelerating: null,
  quarterly_revenue_accelerating: null,
  institutional_holders: null,
  institutional_ownership_pct: null,
  next_earnings_date: null,
  beta: null,
  eps_quarter_history: [],
  annual_eps_history: []
};

export function StockFundamentalsPanel({ ticker }: { ticker: string }) {
  const clean = ticker.toUpperCase();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<FundamentalsForm | null>(null);

  const query = useQuery({
    queryKey: ["stock-fundamentals", clean],
    queryFn: () => api.stockFundamentals(clean),
    staleTime: 60_000
  });

  const serverForm = useMemo(() => fromItem(query.data?.item, clean), [clean, query.data?.item]);
  const form = draft ?? serverForm;
  const dirty = draft !== null;

  const scorePreview = useMemo(() => previewFundamentalScore(form), [form]);
  const earningsTone = useMemo(() => toneForEarnings(form.next_earnings_date), [form.next_earnings_date]);

  const mutation = useMutation({
    mutationFn: () => api.updateStockFundamentals(clean, toPayload(form)),
    onSuccess: () => {
      setDraft(null);
      void queryClient.invalidateQueries({ queryKey: ["stock-fundamentals", clean] });
      void queryClient.invalidateQueries({ queryKey: ["stock-assessment", clean] });
      void queryClient.invalidateQueries({ queryKey: ["stock-assessment-ranking"] });
    }
  });

  const setField = <K extends keyof FundamentalsForm>(key: K, value: FundamentalsForm[K]) => {
    setDraft((current) => ({ ...(current ?? serverForm), [key]: value }));
  };
  const setEpsHistoryField = <K extends keyof StockFundamentalsEpsQuarter>(
    index: number,
    key: K,
    value: StockFundamentalsEpsQuarter[K]
  ) => {
    setDraft((current) => {
      const base = current ?? serverForm;
      const nextHistory = padEpsHistory(base.eps_quarter_history).map((item, itemIndex) =>
        itemIndex === index ? { ...item, [key]: value } : item
      );
      return { ...base, eps_quarter_history: nextHistory };
    });
  };
  const setAnnualEpsHistoryField = <K extends keyof StockFundamentalsAnnualEps>(
    index: number,
    key: K,
    value: StockFundamentalsAnnualEps[K]
  ) => {
    setDraft((current) => {
      const base = current ?? serverForm;
      const nextHistory = padAnnualEpsHistory(base.annual_eps_history).map((item, itemIndex) =>
        itemIndex === index ? { ...item, [key]: value } : item
      );
      return { ...base, annual_eps_history: nextHistory };
    });
  };

  return (
    <section className="rounded border border-[#2d333d] bg-[#171a20] p-5">
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Database className="size-5 text-[#8ea4c8]" />
            <h2 className="text-lg font-semibold">Fundamental-Cache</h2>
          </div>
          <p className="mt-1 text-sm text-[#a0a7b4]">
            {query.data?.item
              ? `Stand ${query.data.item.as_of} · ${query.data.item.source}`
              : "Noch kein gespeicherter Fundamentals-Datensatz."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip tone={query.data?.item ? "good" : "warning"}>
            {query.data?.item ? "gespeichert" : "leer"}
          </StatusChip>
          <StatusChip tone={toneForScore(scorePreview)}>{Math.round(scorePreview)}/100</StatusChip>
          {dirty && <StatusChip tone="warning">ungespeichert</StatusChip>}
        </div>
      </div>

      {query.isError && (
        <div className="mb-4 rounded border border-rose-300/25 bg-rose-950/20 p-3 text-sm text-rose-100">
          Fundamentals konnten nicht geladen werden.
        </div>
      )}

      <div className="grid gap-3 xl:grid-cols-4">
        <TextField label="Quelle" value={form.source} onChange={(value) => setField("source", value)} />
        <TextField label="Stichtag" type="date" value={form.as_of ?? ""} onChange={(value) => setField("as_of", value)} />
        <TextField
          label="Geschäftsperiode"
          value={form.fiscal_period ?? ""}
          onChange={(value) => setField("fiscal_period", value)}
          placeholder="Q1 2026"
        />
        <TextField
          label="Nächste Earnings"
          type="date"
          value={form.next_earnings_date ?? ""}
          onChange={(value) => setField("next_earnings_date", value || null)}
          tone={earningsTone}
        />
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <NumberField label="EPS YoY Q Kurzfeld" suffix="%" value={form.quarterly_eps_growth_pct} onChange={(value) => setField("quarterly_eps_growth_pct", value)} />
        <NumberField label="EPS YoY Jahr Kurzfeld" suffix="%" value={form.annual_eps_growth_pct} onChange={(value) => setField("annual_eps_growth_pct", value)} />
        <BooleanField label="EPS beschleunigt Bonus" value={form.quarterly_eps_accelerating} onChange={(value) => setField("quarterly_eps_accelerating", value)} />
        <NumberField label="Summe EPS 4Q" prefix="$" value={form.trailing_eps} onChange={(value) => setField("trailing_eps", value)} />
      </div>

      <div className="mt-3 rounded border border-[#242a33] bg-[#111419] p-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <h3 className="text-sm font-semibold">EPS-Historie letzte 3 Jahre</h3>
            <p className="mt-1 text-xs leading-5 text-[#7f8794]">
              Das jährliche EPS-Kriterium besteht nur, wenn jedes der drei Jahre mindestens +20% YoY liefert.
            </p>
          </div>
          <StatusChip tone={annualEpsHistoryTone(form.annual_eps_history)}>{annualEpsHistorySummary(form.annual_eps_history)}</StatusChip>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {padAnnualEpsHistory(form.annual_eps_history).map((item, index) => (
            <div key={index} className="rounded border border-[#2d333d] bg-[#171a20] p-3">
              <TextField
                label={`Jahr ${index + 1}`}
                value={item.fiscal_year}
                onChange={(value) => setAnnualEpsHistoryField(index, "fiscal_year", value)}
                placeholder={`${new Date().getFullYear() - index - 1}`}
              />
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-1 2xl:grid-cols-2">
                <NumberField
                  label="EPS Jahr"
                  value={item.eps_current_year}
                  onChange={(value) => setAnnualEpsHistoryField(index, "eps_current_year", value)}
                />
                <NumberField
                  label="EPS Vorjahr"
                  value={item.eps_previous_year}
                  onChange={(value) => setAnnualEpsHistoryField(index, "eps_previous_year", value)}
                />
              </div>
              <div className="mt-3 text-xs text-[#a0a7b4]">
                YoY: <span className={epsGrowthClass(computeAnnualEpsGrowth(item))}>{formatSignedPct(computeAnnualEpsGrowth(item))}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 rounded border border-[#242a33] bg-[#111419] p-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <h3 className="text-sm font-semibold">EPS-Historie letzte 3 Quartale</h3>
            <p className="mt-1 text-xs leading-5 text-[#7f8794]">
              Das EPS-Kriterium besteht nur, wenn alle drei Quartale jeweils mindestens +20% YoY liefern.
            </p>
          </div>
          <StatusChip tone={epsHistoryTone(form.eps_quarter_history)}>{epsHistorySummary(form.eps_quarter_history)}</StatusChip>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {padEpsHistory(form.eps_quarter_history).map((item, index) => (
            <div key={index} className="rounded border border-[#2d333d] bg-[#171a20] p-3">
              <TextField
                label={`Quartal ${index + 1}`}
                value={item.fiscal_period}
                onChange={(value) => setEpsHistoryField(index, "fiscal_period", value)}
                placeholder={`Q${index + 1} 2026`}
              />
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-1 2xl:grid-cols-2">
                <NumberField
                  label="EPS aktuell"
                  value={item.eps_current_quarter}
                  onChange={(value) => setEpsHistoryField(index, "eps_current_quarter", value)}
                />
                <NumberField
                  label="EPS Vorjahr"
                  value={item.eps_same_quarter_last_year}
                  onChange={(value) => setEpsHistoryField(index, "eps_same_quarter_last_year", value)}
                />
              </div>
              <div className="mt-3 text-xs text-[#a0a7b4]">
                YoY: <span className={epsGrowthClass(computeEpsGrowth(item))}>{formatSignedPct(computeEpsGrowth(item))}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <NumberField label="Umsatz YoY Q" suffix="%" value={form.quarterly_revenue_growth_pct} onChange={(value) => setField("quarterly_revenue_growth_pct", value)} />
        <NumberField label="Umsatz YoY Jahr" suffix="%" value={form.annual_revenue_growth_pct} onChange={(value) => setField("annual_revenue_growth_pct", value)} />
        <BooleanField label="Umsatz beschleunigt" value={form.quarterly_revenue_accelerating} onChange={(value) => setField("quarterly_revenue_accelerating", value)} />
        <NumberField label="ROE" suffix="%" value={form.roe_pct} onChange={(value) => setField("roe_pct", value)} />
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <NumberField label="Gewinnmarge" suffix="%" value={form.profit_margin_pct} onChange={(value) => setField("profit_margin_pct", value)} />
        <NumberField label="Institutionen" value={form.institutional_holders} onChange={(value) => setField("institutional_holders", value)} integer />
        <NumberField label="Inst. gehalten" suffix="%" value={form.institutional_ownership_pct} onChange={(value) => setField("institutional_ownership_pct", value)} />
        <NumberField label="Beta" value={form.beta} onChange={(value) => setField("beta", value)} />
      </div>

      <div className="mt-5 flex flex-col gap-3 border-t border-[#242a33] pt-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2 text-sm text-[#a0a7b4]">
          <CalendarClock className="size-4" />
          <span>{earningsHint(form.next_earnings_date)}</span>
        </div>
        <button
          className="inline-flex h-10 items-center justify-center gap-2 rounded border border-emerald-300/30 bg-emerald-400/10 px-4 text-sm font-medium text-emerald-100 transition hover:bg-emerald-400/15 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
          type="button"
        >
          <Save className="size-4" />
          {mutation.isPending ? "Speichert" : "Speichern"}
        </button>
      </div>

      {mutation.isError && (
        <div className="mt-3 rounded border border-rose-300/25 bg-rose-950/20 p-3 text-sm text-rose-100">
          Speichern fehlgeschlagen. Prüfe Backend und Datenbankverbindung.
        </div>
      )}
      {mutation.isSuccess && !dirty && (
        <div className="mt-3 rounded border border-emerald-300/20 bg-emerald-950/20 p-3 text-sm text-emerald-100">
          Fundamentals gespeichert. Assessment und Ranking werden aktualisiert.
        </div>
      )}
    </section>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  tone = "neutral"
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: "text" | "date";
  tone?: Tone;
}) {
  return (
    <label className="block rounded border border-[#242a33] bg-[#111419] p-3">
      <span className="mb-2 block text-xs uppercase text-[#a0a7b4]">{label}</span>
      <input
        className={`h-9 w-full rounded border bg-[#171a20] px-3 text-sm outline-none transition ${inputTone(tone)}`}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        type={type}
        value={value}
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
  prefix = "",
  suffix = "",
  integer = false
}: {
  label: string;
  value?: number | null;
  onChange: (value: number | null) => void;
  prefix?: string;
  suffix?: string;
  integer?: boolean;
}) {
  return (
    <label className="block rounded border border-[#242a33] bg-[#111419] p-3">
      <span className="mb-2 block text-xs uppercase text-[#a0a7b4]">{label}</span>
      <div className="flex h-9 items-center rounded border border-[#2d333d] bg-[#171a20] px-3 focus-within:border-sky-300/50">
        {prefix && <span className="mr-1 text-sm text-[#7f8794]">{prefix}</span>}
        <input
          className="min-w-0 flex-1 bg-transparent text-sm outline-none"
          inputMode="decimal"
          onChange={(event) => onChange(parseNumber(event.target.value, integer))}
          type="number"
          value={value ?? ""}
        />
        {suffix && <span className="ml-1 text-sm text-[#7f8794]">{suffix}</span>}
      </div>
    </label>
  );
}

function BooleanField({
  label,
  value,
  onChange
}: {
  label: string;
  value?: boolean | null;
  onChange: (value: boolean | null) => void;
}) {
  return (
    <label className="block rounded border border-[#242a33] bg-[#111419] p-3">
      <span className="mb-2 block text-xs uppercase text-[#a0a7b4]">{label}</span>
      <select
        className="h-9 w-full rounded border border-[#2d333d] bg-[#171a20] px-3 text-sm outline-none transition focus:border-sky-300/50"
        onChange={(event) => onChange(event.target.value === "unknown" ? null : event.target.value === "yes")}
        value={value === null || value === undefined ? "unknown" : value ? "yes" : "no"}
      >
        <option value="unknown">unbekannt</option>
        <option value="yes">ja</option>
        <option value="no">nein</option>
      </select>
    </label>
  );
}

function fromItem(item: StockFundamentalsItem | null | undefined, ticker: string): FundamentalsForm {
  if (!item) {
    return {
      ...emptyForm,
      as_of: new Date().toISOString().slice(0, 10),
      fiscal_period: "",
      source: "manual"
    };
  }
  return {
    ...emptyForm,
    ...item,
    as_of: item.as_of || new Date().toISOString().slice(0, 10),
    source: item.source || "manual",
    fiscal_period: item.fiscal_period || `${ticker} fundamentals`,
    next_earnings_date: item.next_earnings_date ?? null,
    eps_quarter_history: item.eps_quarter_history ?? [],
    annual_eps_history: item.annual_eps_history ?? []
  };
}

function toPayload(form: FundamentalsForm): StockFundamentalsUpdate {
  const epsQuarterHistory = form.eps_quarter_history
    .map((item) => ({
      ...item,
      eps_growth_yoy_pct: computeEpsGrowth(item)
    }))
    .filter(
      (item) =>
        item.fiscal_period.trim() ||
        item.eps_current_quarter !== null ||
        item.eps_same_quarter_last_year !== null
    );
  const annualEpsHistory = form.annual_eps_history
    .map((item) => ({
      ...item,
      eps_growth_yoy_pct: computeAnnualEpsGrowth(item)
    }))
    .filter((item) => item.fiscal_year.trim() || item.eps_current_year !== null || item.eps_previous_year !== null);
  return {
    ...form,
    quarterly_eps_growth_pct: epsQuarterHistory[0]?.eps_growth_yoy_pct ?? form.quarterly_eps_growth_pct,
    annual_eps_growth_pct: annualEpsHistory[0]?.eps_growth_yoy_pct ?? form.annual_eps_growth_pct,
    source: form.source.trim() || "manual",
    fiscal_period: form.fiscal_period.trim(),
    as_of: form.as_of || null,
    next_earnings_date: form.next_earnings_date || null,
    eps_quarter_history: epsQuarterHistory,
    annual_eps_history: annualEpsHistory
  };
}

function parseNumber(value: string, integer: boolean) {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return integer ? Math.round(parsed) : parsed;
}

function previewFundamentalScore(form: FundamentalsForm) {
  const checks = [
    epsHistoryScore(form.eps_quarter_history),
    form.quarterly_eps_accelerating === true ? 1 : 0,
    annualEpsHistoryScore(form.annual_eps_history),
    (form.trailing_eps ?? -Infinity) > 0 ? 1 : 0,
    (form.quarterly_revenue_growth_pct ?? -Infinity) >= 20 ? 1 : 0,
    form.quarterly_revenue_accelerating === true ? 1 : 0,
    (form.annual_revenue_growth_pct ?? -Infinity) >= 20 ? 1 : 0,
    (form.roe_pct ?? -Infinity) >= 17 ? 1 : 0,
    (form.profit_margin_pct ?? -Infinity) > 0 ? 1 : 0
  ];
  return (checks.reduce((sum, value) => sum + value, 0) / checks.length) * 100;
}

function padEpsHistory(history: StockFundamentalsEpsQuarter[]) {
  const rows = history.slice(0, 3).map((item) => ({
    fiscal_period: item.fiscal_period ?? "",
    eps_current_quarter: item.eps_current_quarter ?? null,
    eps_same_quarter_last_year: item.eps_same_quarter_last_year ?? null,
    eps_growth_yoy_pct: item.eps_growth_yoy_pct ?? null,
    flag: item.flag ?? null
  }));
  while (rows.length < 3) {
    rows.push({
      fiscal_period: "",
      eps_current_quarter: null,
      eps_same_quarter_last_year: null,
      eps_growth_yoy_pct: null,
      flag: null
    });
  }
  return rows;
}

function epsHistoryScore(history: StockFundamentalsEpsQuarter[]) {
  const values = padEpsHistory(history).map(computeEpsGrowth);
  if (values.some((value) => value === null)) return 0;
  return values.filter((value) => value !== null && value >= 20).length / 3;
}

function epsHistoryTone(history: StockFundamentalsEpsQuarter[]): Tone {
  const values = padEpsHistory(history).map(computeEpsGrowth);
  if (values.every((value) => value !== null && value >= 20)) return "good";
  if (values.some((value) => value !== null && value >= 20)) return "warning";
  return "neutral";
}

function epsHistorySummary(history: StockFundamentalsEpsQuarter[]) {
  const values = padEpsHistory(history).map(computeEpsGrowth);
  const valid = values.filter((value) => value !== null);
  const passed = valid.filter((value) => value >= 20).length;
  if (valid.length < 3) return `${valid.length}/3 verfügbar`;
  return `${passed}/3 >=20%`;
}

function padAnnualEpsHistory(history: StockFundamentalsAnnualEps[]) {
  const rows = history.slice(0, 3).map((item) => ({
    fiscal_year: item.fiscal_year ?? "",
    eps_current_year: item.eps_current_year ?? null,
    eps_previous_year: item.eps_previous_year ?? null,
    eps_growth_yoy_pct: item.eps_growth_yoy_pct ?? null,
    flag: item.flag ?? null
  }));
  while (rows.length < 3) {
    rows.push({
      fiscal_year: "",
      eps_current_year: null,
      eps_previous_year: null,
      eps_growth_yoy_pct: null,
      flag: null
    });
  }
  return rows;
}

function annualEpsHistoryScore(history: StockFundamentalsAnnualEps[]) {
  const values = padAnnualEpsHistory(history).map(computeAnnualEpsGrowth);
  if (values.some((value) => value === null)) return 0;
  return values.filter((value) => value !== null && value >= 20).length / 3;
}

function annualEpsHistoryTone(history: StockFundamentalsAnnualEps[]): Tone {
  const values = padAnnualEpsHistory(history).map(computeAnnualEpsGrowth);
  if (values.every((value) => value !== null && value >= 20)) return "good";
  if (values.some((value) => value !== null && value >= 20)) return "warning";
  return "neutral";
}

function annualEpsHistorySummary(history: StockFundamentalsAnnualEps[]) {
  const values = padAnnualEpsHistory(history).map(computeAnnualEpsGrowth);
  const valid = values.filter((value) => value !== null);
  const passed = valid.filter((value) => value >= 20).length;
  if (valid.length < 3) return `${valid.length}/3 verfügbar`;
  return `${passed}/3 >=20%`;
}

function computeEpsGrowth(item: StockFundamentalsEpsQuarter) {
  const current = item.eps_current_quarter;
  const previous = item.eps_same_quarter_last_year;
  if (typeof current !== "number" || typeof previous !== "number" || previous <= 0) {
    return item.eps_growth_yoy_pct ?? null;
  }
  return Math.round((current / previous - 1) * 1000) / 10;
}

function computeAnnualEpsGrowth(item: StockFundamentalsAnnualEps) {
  const current = item.eps_current_year;
  const previous = item.eps_previous_year;
  if (typeof current !== "number" || typeof previous !== "number" || previous <= 0) {
    return item.eps_growth_yoy_pct ?? null;
  }
  return Math.round((current / previous - 1) * 1000) / 10;
}

function formatSignedPct(value: number | null) {
  if (value === null || Number.isNaN(value)) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function epsGrowthClass(value: number | null) {
  if (value === null) return "text-[#7f8794]";
  return value >= 20 ? "font-medium text-emerald-200" : "font-medium text-amber-200";
}

function toneForScore(value: number): Tone {
  if (value >= 75) return "good";
  if (value >= 55) return "warning";
  if (value >= 45) return "neutral";
  return "bad";
}

function toneForEarnings(value?: string | null): Tone {
  if (!value) return "neutral";
  const days = daysUntil(value);
  if (days === null) return "neutral";
  if (days <= 7) return "bad";
  if (days <= 21) return "warning";
  return "good";
}

function earningsHint(value?: string | null) {
  if (!value) return "Kein Earnings-Termin gespeichert.";
  const days = daysUntil(value);
  if (days === null) return "Earnings-Termin ist nicht lesbar.";
  if (days < 0) return `Earnings-Termin liegt ${Math.abs(days)} Kalendertage zurück.`;
  if (days === 0) return "Earnings-Termin ist heute.";
  return `Earnings in ${days} Kalendertagen.`;
}

function daysUntil(value: string) {
  const target = new Date(`${value}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;
  const today = new Date();
  const localToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((target.getTime() - localToday.getTime()) / 86_400_000);
}

function inputTone(tone: Tone) {
  if (tone === "good") return "border-emerald-300/30 focus:border-emerald-300/60";
  if (tone === "warning") return "border-amber-300/30 focus:border-amber-300/60";
  if (tone === "bad") return "border-rose-300/30 focus:border-rose-300/60";
  return "border-[#2d333d] focus:border-sky-300/50";
}
