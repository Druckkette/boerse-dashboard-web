"use client";
import { useEffect, useState } from "react";
export function ResearchTableTools({
  id,
  columns,
  pinned = 1,
}: {
  id: "screening" | "rs" | "compare";
  columns: string[];
  pinned?: number;
}) {
  const [hidden, setHidden] = useState<number[]>([]),
    [compact, setCompact] = useState(false);
  useEffect(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem(`research-columns:${id}`) || "{}",
      );
      // Browser-only presentation preferences are restored after hydration.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setHidden(
        Array.isArray(saved.hidden)
          ? saved.hidden.filter(
              (i: unknown) =>
                typeof i === "number" &&
                Number.isInteger(i) &&
                i >= pinned &&
                i < columns.length,
            )
          : [],
      );
      setCompact(saved.compact === true);
    } catch {
      /* Use the complete, comfortable table. */
    }
  }, [id, pinned, columns.length]);
  function persist(next: number[], dense: boolean) {
    setHidden(next);
    setCompact(dense);
    try {
      localStorage.setItem(
        `research-columns:${id}`,
        JSON.stringify({ hidden: next, compact: dense }),
      );
    } catch {
      /* Preferences remain usable in this session. */
    }
  }
  return (
    <>
      <details className="hidden rounded-lg border border-[#e3e8ef] p-3 text-sm lg:block">
        <summary className="cursor-pointer font-semibold">
          Spalten & Lesedichte
        </summary>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2">
          {columns.map((label, index) => (
            <label
              key={`${index}:${label}`}
              className="flex items-center gap-2"
            >
              <input
                type="checkbox"
                checked={!hidden.includes(index)}
                disabled={index < pinned}
                onChange={(e) =>
                  persist(
                    e.target.checked
                      ? hidden.filter((i) => i !== index)
                      : [...hidden, index],
                    compact,
                  )
                }
              />
              {label}
            </label>
          ))}
        </div>
        <label className="mt-3 flex items-center gap-2">
          <input
            type="checkbox"
            checked={compact}
            onChange={(e) => persist(hidden, e.target.checked)}
          />
          Kompakte Zeilen
        </label>
        <p className="mt-2 text-[#526174]">
          Auswahl wird in diesem Browser gespeichert. Aktienkennung bleibt
          sichtbar.
        </p>
      </details>
      <style>
        {hidden
          .map(
            (index) =>
              `table[data-research="${id}"] tr > :nth-child(${index + 1}){display:none}`,
          )
          .join("\n") +
          (compact
            ? `table[data-research="${id}"] :is(th,td){padding-top:6px;padding-bottom:6px}`
            : "")}
      </style>
    </>
  );
}
