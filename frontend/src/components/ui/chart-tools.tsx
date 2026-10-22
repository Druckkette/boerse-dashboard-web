"use client";
import { useEffect, useState } from "react";
import type { ChartLevel } from "./line-chart-card";

type Preferences = { logarithmic: boolean; levels: ChartLevel[] };
const defaults: Preferences = { logarithmic: false, levels: [] };
function decode(raw: string | null): Preferences {
  try {
    const value = JSON.parse(raw || "null");
    if (
      !value ||
      typeof value.logarithmic !== "boolean" ||
      !Array.isArray(value.levels)
    )
      return defaults;
    return {
      logarithmic: value.logarithmic,
      levels: value.levels
        .filter(
          (r: ChartLevel) =>
            r &&
            typeof r.key === "string" &&
            typeof r.label === "string" &&
            r.label.length <= 40 &&
            Number.isFinite(r.value) &&
            r.value > 0,
        )
        .slice(0, 20)
        .map((r: ChartLevel) => ({ ...r, color: "#9333ea" })),
    };
  } catch {
    return defaults;
  }
}
export function useChartPreferences(key: string) {
  const [value, setValue] = useState(defaults),
    [loadedKey, setLoadedKey] = useState("");
  useEffect(() => {
    let next = defaults;
    try {
      next = decode(localStorage.getItem(`chart-preferences:${key}`));
    } catch {
      /* Browser storage is optional. */
    }
    // Restore a browser preference only after hydration, never financial data.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setValue(next);
    setLoadedKey(key);
  }, [key]);
  function update(next: Preferences) {
    setValue(next);
    try {
      localStorage.setItem(`chart-preferences:${key}`, JSON.stringify(next));
    } catch {
      /* The current chart remains editable. */
    }
  }
  return { value: loadedKey === key ? value : defaults, update };
}
export function ChartTools({
  value,
  onChange,
  canLog,
  onExport,
}: {
  value: Preferences;
  onChange: (value: Preferences) => void;
  canLog: boolean;
  onExport: (format: "svg" | "png") => Promise<void>;
}) {
  const [label, setLabel] = useState(""),
    [level, setLevel] = useState(""),
    [name, setName] = useState(""),
    [error, setError] = useState("");
  const [templates, setTemplates] = useState<
    { name: string; value: Preferences }[]
  >([]);
  function load() {
    try {
      const raw = JSON.parse(
        localStorage.getItem("chart-templates:v1") || "[]",
      );
      setTemplates(
        Array.isArray(raw)
          ? raw
              .filter((v) => typeof v.name === "string")
              .slice(0, 20)
              .map((v) => ({
                name: v.name,
                value: decode(JSON.stringify(v.value)),
              }))
          : [],
      );
    } catch {
      setTemplates([]);
    }
  }
  return (
    <details
      className="my-3 rounded-lg border border-[#e3e8ef] p-3 text-sm"
      onToggle={(event) => {
        if (event.currentTarget.open) load();
      }}
    >
      <summary className="cursor-pointer font-semibold">
        Chartwerkzeuge · Marken, Vorlagen & Export
      </summary>
      <div className="mt-3 space-y-3">
        <p className="text-[#526174]">
          Marken und Vorlagen werden in diesem Browser gespeichert.
        </p>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            disabled={!canLog}
            checked={value.logarithmic && canLog}
            onChange={(e) =>
              onChange({ ...value, logarithmic: e.target.checked })
            }
          />
          Logarithmische Preisskala
        </label>
        {!canLog && (
          <p className="text-[#526174]">
            Für die logarithmische Skala müssen alle angezeigten Preiswerte
            positiv sein.
          </p>
        )}
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const number = Number(level);
            if (!Number.isFinite(number) || number <= 0) return;
            onChange({
              ...value,
              levels: [
                ...value.levels,
                {
                  key: crypto.randomUUID(),
                  label: label.trim() || "Eigene Marke",
                  value: number,
                  color: "#9333ea",
                },
              ],
            });
            setLabel("");
            setLevel("");
          }}
        >
          <label className="grid gap-1">
            Bezeichnung
            <input
              className="input-dark"
              value={label}
              maxLength={40}
              onChange={(e) => setLabel(e.target.value)}
            />
          </label>
          <label className="grid gap-1">
            Horizontale Kursmarke
            <input
              className="input-dark"
              type="number"
              min="0.000001"
              step="any"
              required
              value={level}
              onChange={(e) => setLevel(e.target.value)}
            />
          </label>
          <button className="app-button" disabled={value.levels.length >= 20}>
            Marke hinzufügen
          </button>
        </form>
        {value.levels.map((row) => (
          <div
            key={row.key}
            className="flex flex-wrap items-center justify-between gap-2"
          >
            <span>
              {row.label} ·{" "}
              {row.value.toLocaleString("de-DE", { maximumFractionDigits: 6 })}
            </span>
            <button
              type="button"
              className="app-button"
              onClick={() =>
                onChange({
                  ...value,
                  levels: value.levels.filter((item) => item.key !== row.key),
                })
              }
            >
              Marke entfernen
            </button>
          </div>
        ))}
        <div className="flex flex-wrap items-end gap-2">
          <label className="grid gap-1">
            Vorlagenname
            <input
              className="input-dark"
              maxLength={60}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="app-button"
            disabled={!name.trim()}
            onClick={() => {
              const next = [
                ...templates.filter((t) => t.name !== name.trim()),
                { name: name.trim(), value },
              ].slice(-20);
              try {
                localStorage.setItem(
                  "chart-templates:v1",
                  JSON.stringify(next),
                );
                setTemplates(next);
                setName("");
                setError("");
              } catch {
                setError(
                  "Die Vorlage konnte in diesem Browser nicht gespeichert werden.",
                );
              }
            }}
          >
            Vorlage speichern
          </button>
          {templates.map((template) => (
            <button
              key={template.name}
              type="button"
              className="app-button"
              onClick={() => onChange(template.value)}
            >
              {template.name} anwenden
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {(["svg", "png"] as const).map((format) => (
            <button
              key={format}
              type="button"
              className="app-button"
              onClick={() => {
                void onExport(format).catch(() =>
                  setError("Chart konnte nicht exportiert werden."),
                );
              }}
            >
              Chart als {format.toUpperCase()} speichern
            </button>
          ))}
        </div>
        {error && (
          <p role="alert" className="text-red-800">
            {error}
          </p>
        )}
      </div>
    </details>
  );
}

export async function exportChart(
  element: HTMLElement | null,
  title: string,
  caption: string,
  format: "svg" | "png",
) {
  const original = element?.querySelector('svg[role="img"]');
  if (!(original instanceof SVGSVGElement)) throw new Error("Chart fehlt");
  const svg = original.cloneNode(true) as SVGSVGElement;
  svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const viewBox = original.viewBox.baseVal;
  svg.setAttribute("width", String(Math.round(viewBox.width)));
  svg.setAttribute("height", String(Math.round(viewBox.height)));
  const description = document.createElementNS(
    "http://www.w3.org/2000/svg",
    "desc",
  );
  description.textContent = `${title} · ${caption}`;
  svg.prepend(description);
  const styles = getComputedStyle(document.documentElement);
  const source = new XMLSerializer()
    .serializeToString(svg)
    .replace(
      /var\((--[a-z-]+)\)/g,
      (_, key) => styles.getPropertyValue(key).trim() || "#172033",
    );
  let blob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
  if (format === "png") {
    const image = new Image(),
      url = URL.createObjectURL(blob);
    try {
      await new Promise<void>((resolve, reject) => {
        image.onload = () => resolve();
        image.onerror = reject;
        image.src = url;
      });
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(viewBox.width * 2);
      canvas.height = Math.round(viewBox.height * 2);
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas fehlt");
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      blob = await new Promise<Blob>((resolve, reject) =>
        canvas.toBlob(
          (value) =>
            value ? resolve(value) : reject(new Error("Export fehlgeschlagen")),
          "image/png",
        ),
      );
    } finally {
      URL.revokeObjectURL(url);
    }
  }
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download = `${title.replace(/[^\p{L}\p{N}_-]+/gu, "-")}.${format}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
