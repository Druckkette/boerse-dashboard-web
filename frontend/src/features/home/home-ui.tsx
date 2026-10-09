import { ArrowRight, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import type { Tone } from "@/lib/types/api";

export const number = (value: number | null | undefined, digits = 0) => value == null ? "–"
  : value.toLocaleString("de-DE", { maximumFractionDigits: digits, minimumFractionDigits: digits });
export const shortDate = (value?: string | null) => value
  ? new Date(`${value}T12:00:00`).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" }) : "–";
export const signedPercent = (value: number | null | undefined, digits = 2) => value == null
  ? "–" : `${value >= 0 ? "+" : ""}${number(value, digits)} %`;
export function marketTone(phase?: string | null): Tone {
  return phase === "aufwaertstrend" || phase === "gruen" ? "good" : phase === "rot" ? "bad"
    : phase === "gelb_startschuss" || phase === "gelb_rally_unter_druck" || phase === "gelb_trend_unter_druck" || phase === "mixed" ? "warning" : "neutral";
}
export function Panel({ id, icon: Icon, title, detail, action, children }: {
  id?: string; icon: LucideIcon; title: string; detail?: string; action?: ReactNode; children: ReactNode;
}) {
  return <section id={id} className="dashboard-section scroll-mt-28 !p-5 md:!p-6">
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-start gap-2.5"><Icon className="mt-0.5 shrink-0 text-[#0f766e]" size={18} />
        <div><h2 className="font-semibold text-[#172033]">{title}</h2>
          {detail && <p className="mt-1 text-xs leading-5 text-[#687386]">{detail}</p>}</div></div>{action}
    </div>{children}
  </section>;
}
export function TextLink({ href, children }: { href: string; children: ReactNode }) {
  return <Link href={href} className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#0f766e] hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#0f766e]">{children}<ArrowRight size={13} /></Link>;
}
export function Empty({ text }: { text: string }) {
  return <p className="rounded-xl bg-[#f7f9fb] px-4 py-3 text-sm leading-6 text-[#687386]">{text}</p>;
}
