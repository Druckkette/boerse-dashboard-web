"use client";

import { useRef, useState } from "react";
import { Download, Loader2 } from "lucide-react";

export function ReportExportButton({ ticker, tradeId }: { ticker: string; tradeId?: string }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  async function download() {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setError(null);
    try {
      const base = (process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1").replace(/\/$/, "");
      const query = tradeId ? `?trade_id=${encodeURIComponent(tradeId)}` : "";
      const response = await fetch(`${base}/stocks/${encodeURIComponent(ticker)}/report.pdf${query}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(120_000)
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(typeof payload?.detail === "string" ? payload.detail : "PDF konnte nicht erzeugt werden. Bitte erneut versuchen.");
      }
      if (!response.headers.get("content-type")?.includes("application/pdf")) {
        throw new Error("Der Server hat keinen PDF-Bericht geliefert. Bitte erneut anmelden und versuchen.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${ticker.replace(/[^A-Za-z0-9.-]/g, "_")}-${tradeId ? "Trade" : "Investment"}-Report.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Leave enough time for desktop browsers to acquire the download.
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (cause) {
      setError(cause instanceof Error && cause.name !== "TimeoutError" ? cause.message : "Zeitlimit beim PDF-Export erreicht. Bitte erneut versuchen.");
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <button type="button" onClick={() => void download()} disabled={pending} aria-busy={pending}
        className="inline-flex items-center gap-2 rounded-[10px] border border-[#0f766e]/30 bg-[#e6f5f2] px-3 py-2 text-sm font-medium text-[#0f766e] hover:bg-[#d5eee8] disabled:cursor-wait disabled:opacity-60">
        {pending ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
        {pending ? "PDF wird erstellt …" : "Als PDF exportieren"}
      </button>
      {error ? <p role="alert" className="max-w-sm text-sm text-[#c2413b]">{error}</p> : null}
    </div>
  );
}
