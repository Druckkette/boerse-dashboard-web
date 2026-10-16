"use client";
import Link from "next/link";
import type { IndustryGroupRankingRow } from "@/lib/types/api";

export function IndustryRotation({ rows, asOf, benchmark, window, selected, onWindow: setWindow, onSelect: setSelected }: { rows: IndustryGroupRankingRow[]; asOf: string; benchmark: string; window: 5 | 20; selected: string | null; onWindow: (value: 5 | 20) => void; onSelect: (value: string | null) => void }) {
  const points = rows.filter(row => row.is_ranked && row.rs_score != null && (window === 5 ? row.rs_change_5d : row.rs_change_20d) != null);
  const extent = Math.max(5, ...points.map(row => Math.abs((window === 5 ? row.rs_change_5d : row.rs_change_20d)!))) * 1.15;
  const x = (value: number) => 65 + Math.max(0, Math.min(100, value)) * 7.65;
  const y = (value: number) => 200 - value / extent * 145;
  const active = points.find(row => row.code === selected);
  const history = active?.rotation_history ?? [];
  const trail = history.map((point, index) => {
    const previous = history[index - window];
    if (!point.is_ranked || point.rs_score == null || previous?.rs_score == null || previous.ranked_group_count !== point.ranked_group_count) return null;
    return { date: point.date, score: point.rs_score, change: point.rs_score - previous.rs_score };
  });
  const trailPath = trail.map((point, index) => point ? `${index === 0 || !trail[index - 1] ? "M" : "L"}${x(point.score)},${y(point.change)}` : "").join(" ");
  return <section className="dashboard-section">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Branchenrotation</h2><p className="mt-1 text-xs text-[#687386]">Stärke und Veränderung des RS-Scores · {asOf} · Benchmark {benchmark}</p></div><label className="text-sm">Vergleich <select className="input-dark ml-2 !w-auto" value={window} onChange={event => setWindow(Number(event.target.value) as 5 | 20)}><option value={5}>5 gespeicherte Stände</option><option value={20}>20 gespeicherte Stände</option></select></label></div>
    {!points.length ? <p className="app-notice mt-4">Noch keine vollständigen historischen Vergleichspaare für diese Auswahl. Kleine oder unvollständige Gruppen erhalten keinen offiziellen Rotationspunkt.</p> : <>
      <svg viewBox="0 0 900 410" className="mt-3 w-full" role="img" aria-label="Branchen-RS und dessen Veränderung: rechts stärker, oben zunehmend">
        <rect x="65" y="45" width="765" height="155" fill="#eaf7ef" /><rect x="65" y="200" width="765" height="150" fill="#fff8eb" />
        {[0, 25, 50, 75, 100].map(value => <g key={value}><line x1={x(value)} y1={45} x2={x(value)} y2={350} stroke="#dbe4ed" /><text x={x(value)} y={372} textAnchor="middle" fontSize={12} fill="#687386">{value}</text></g>)}
        <line x1="65" y1="200" x2="830" y2="200" stroke="#94a3b8" /><text x="18" y="57" fontSize={12} fill="#687386">+{extent.toFixed(0)}</text><text x="29" y="204" fontSize={12} fill="#687386">0</text><text x="18" y="350" fontSize={12} fill="#687386">−{extent.toFixed(0)}</text><text x="450" y="400" fontSize={13} textAnchor="middle" fill="#475569">Branchen-RS · 1 bis 100</text>
        {trail.length > 1 && <path d={trailPath} fill="none" stroke="#0f766e" strokeWidth="2" strokeDasharray="4 3" />}
        {points.map(row => <g key={row.code} onClick={() => setSelected(row.code)} className="cursor-pointer"><title>{row.name}: RS {row.rs_score?.toFixed(1)}, Veränderung {(window === 5 ? row.rs_change_5d : row.rs_change_20d)?.toFixed(1)} · {row.member_count} Mitglieder</title><circle cx={x(row.rs_score!)} cy={y((window === 5 ? row.rs_change_5d : row.rs_change_20d)!)} r={Math.min(13, 4 + Math.sqrt(row.member_count) / 2)} fill={selected === row.code ? "#172033" : "#0f766e"} opacity={selected && selected !== row.code ? .3 : .75} /></g>)}
      </svg>
      <label className="block text-sm">Branche hervorheben<select className="input-dark mt-1" value={selected ?? ""} onChange={event => setSelected(event.target.value || null)}><option value="">Alle Branchen</option>{points.map(row => <option key={row.code} value={row.code}>{row.name}</option>)}</select></label>
      {active && <p className="mt-2 text-sm"><Link className="font-semibold text-[#0f766e] underline" href={`/industry-groups/${encodeURIComponent(active.code)}`}>{active.name}</Link> · RS {active.rs_score?.toFixed(1)} · {active.member_count} Mitglieder · {trail.filter(Boolean).length} vergleichbare Spurpunkte</p>}
    </>}
    <p className="mt-3 text-xs leading-5 text-[#687386]">Punktgröße: Gruppengröße. Die Y-Achse zeigt die eigene RS-Veränderung, keine Rangänderung. Spuren werden bei wechselnder Vergleichsgröße unterbrochen. Dieselbe Taxonomie und Algorithmusversion bleiben maßgeblich.</p>
  </section>;
}
