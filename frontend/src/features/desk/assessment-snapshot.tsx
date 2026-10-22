export function AssessmentSnapshot({
  value,
}: {
  value: Record<string, unknown>;
}) {
  const scores =
    value.scores && typeof value.scores === "object"
      ? (value.scores as Record<string, number | null>)
      : {};
  const identity =
    value.calculation && typeof value.calculation === "object"
      ? (value.calculation as Record<string, unknown>)
      : {};
  const checks = Array.isArray(value.checks)
    ? (value.checks.filter((row) => row && typeof row === "object") as {
        label?: string;
        passed?: boolean;
        detail?: string;
      }[])
    : [];
  return (
    <div className="mt-3 space-y-3 rounded-lg bg-slate-50 p-4 text-sm">
      <p>
        Bewertung zum {String(value.as_of || "nicht belegten Stichtag")} ·{" "}
        {String(value.verdict_label || "Keine abschließende Einordnung")}
      </p>
      <p className="text-[#526174]">
        Regelversion {String(identity.version || "nicht hinterlegt")}
        {identity.configuration_hash
          ? ` · Konfiguration ${String(identity.configuration_hash).slice(0, 12)}`
          : ""}
      </p>
      <dl className="grid gap-3 sm:grid-cols-3">
        {Object.entries(scores).map(([key, score]) => (
          <div key={key}>
            <dt className="text-[#526174]">
              {(
                {
                  overall: "Gesamtscore",
                  technical: "Technisch",
                  fundamental: "Fundamental",
                  moving_averages: "Gleitende Durchschnitte",
                  chart_behavior: "Chart",
                } as Record<string, string>
              )[key] || key}
            </dt>
            <dd className="font-semibold">
              {typeof score === "number"
                ? score.toLocaleString("de-DE", { maximumFractionDigits: 1 })
                : "Nicht verfügbar"}
            </dd>
          </div>
        ))}
      </dl>
      {Boolean(value.data_quality) &&
        typeof value.data_quality === "object" && (
          <ul className="space-y-1">
            {Object.entries(
              value.data_quality as Record<
                string,
                { label?: string; status?: string; as_of?: string }
              >,
            ).map(([key, item]) => (
              <li key={key}>
                {item.label || key} ·{" "}
                {item.status === "fresh"
                  ? "aktuell bestätigt"
                  : item.status === "missing"
                    ? "fehlt"
                    : "eingeschränkt"}{" "}
                · {item.as_of || "Stichtag fehlt"}
              </li>
            ))}
          </ul>
        )}
      {checks.length > 0 && (
        <details>
          <summary className="cursor-pointer font-semibold">
            Damals geprüfte Kriterien
          </summary>
          <ul className="mt-2 space-y-2">
            {checks.map((check, index) => (
              <li key={index}>
                <strong>{check.label}</strong> ·{" "}
                {check.passed ? "erfüllt" : "nicht erfüllt"}
                {check.detail && (
                  <p className="text-[#526174]">{check.detail}</p>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
