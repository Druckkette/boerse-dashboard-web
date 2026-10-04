import { assessmentCriteria } from "./assessment-criteria";
import type { CriterionResult } from "./assessment-criterion-results";

const outcomes = { passed: "✓ Erfüllt", failed: "✕ Nicht erfüllt", missing: "– Nicht bewertbar", neutral: "○ Neutral" };
function Results({ rows }: { rows: CriterionResult[] }) {
  return <ul className="mt-2 space-y-2">{rows.map((row, index) => <li key={`${row.label}-${index}`} className="border-l-2 border-[#e3e8ef] pl-2">
    <div className="flex flex-wrap items-center justify-between gap-x-3"><span className="font-medium text-[#172033]">{row.label}{row.weight !== undefined ? ` (${Math.round(row.weight * 1000) / 10} %)` : ""}</span><span className={row.outcome === "passed" ? "text-emerald-700" : row.outcome === "failed" ? "text-rose-700" : "text-[#687386]"}>{outcomes[row.outcome]}</span></div>
    {row.detail ? <p>{row.detail}</p> : null}
    {row.children?.length ? <Results rows={row.children} /> : null}
  </li>)}</ul>;
}
export function AssessmentCriterionNote({ criterion, id, results }: { criterion: string; id?: string; results?: CriterionResult[] }) {
  const note = assessmentCriteria[criterion]?.note;
  if (!note && !results?.length) return null;
  return <details id={id} className="mt-1 text-xs leading-5 text-[#687386]">
    <summary className="cursor-pointer text-[#0f766e]">Bestandteile und Berechnung</summary>
    {results?.length ? <Results rows={results} /> : null}
    {note ? <p className="mt-2">{note}</p> : null}
  </details>;
}
