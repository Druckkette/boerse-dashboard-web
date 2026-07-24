import type { ReactNode } from "react";
import clsx from "clsx";

export type MarketCategoryTone = "early" | "warning" | "breadth" | "sentiment";

export function MarketCategorySection({
  children,
  description,
  marker,
  title,
  tone
}: {
  children: ReactNode;
  description: string;
  marker: string;
  title: string;
  tone: MarketCategoryTone;
}) {
  return (
    <section className={clsx("relative border-y px-3 py-4 sm:px-4", sectionClass(tone))}>
      <span className={clsx("absolute inset-y-0 left-0 w-[3px]", accentClass(tone))} aria-hidden="true" />
      <header className="mb-3 flex items-start gap-3 border-b border-black/[0.06] pb-3">
        <span
          className={clsx(
            "grid size-7 shrink-0 place-items-center rounded-[8px] text-[10px] font-bold tabular-nums",
            markerClass(tone)
          )}
          aria-hidden="true"
        >
          {marker}
        </span>
        <div className="min-w-0">
          <h2 className="text-base font-semibold leading-5 text-[#172033]">{title}</h2>
          <p className="mt-0.5 max-w-4xl text-xs leading-5 text-[#687386]">{description}</p>
        </div>
      </header>
      {children}
    </section>
  );
}

function sectionClass(tone: MarketCategoryTone) {
  if (tone === "early") return "border-[#eadfbd] bg-[#fffcf5]";
  if (tone === "warning") return "border-[#ecd6d3] bg-[#fffafa]";
  if (tone === "breadth") return "border-[#d4e7e3] bg-[#f8fcfb]";
  return "border-[#d8e3f2] bg-[#f8fbff]";
}

function accentClass(tone: MarketCategoryTone) {
  if (tone === "early") return "bg-[#d99a2b]";
  if (tone === "warning") return "bg-[#c2413b]";
  if (tone === "breadth") return "bg-[#0f766e]";
  return "bg-[#2563eb]";
}

function markerClass(tone: MarketCategoryTone) {
  if (tone === "early") return "bg-[#fff1c7] text-[#8a5b10]";
  if (tone === "warning") return "bg-[#fde8e6] text-[#a63732]";
  if (tone === "breadth") return "bg-[#e2f2ef] text-[#0f766e]";
  return "bg-[#e8f0ff] text-[#2563eb]";
}
