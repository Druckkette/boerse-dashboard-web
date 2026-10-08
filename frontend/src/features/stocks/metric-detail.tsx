import { splitMetricDetail } from "./metric-detail-data";

/** Preserve provider text while giving each reporting period its own visual column. */
export function MetricDetail({ text }: { text: string }) {
  const { periods, notes } = splitMetricDetail(text);
  return <div className="min-w-0 space-y-2 text-xs leading-5 text-[#687386]">
    {periods.length > 0 && <dl className="grid gap-2 sm:grid-cols-3">
      {periods.map((period, index) => <div key={index} className="min-w-0 rounded-lg border border-[#e3e8ef] bg-white px-3 py-2">
        <dt className="break-words text-[11px] font-medium text-[#687386]">{period.label}</dt>
        <dd className="mt-1 text-base font-semibold tabular-nums text-[#172033]">{period.value}</dd>
      </div>)}
    </dl>}
    {notes.length > 0 && <ul className="space-y-1">{notes.map((note, index) => <li key={index} className="break-words">{note}</li>)}</ul>}
  </div>;
}
