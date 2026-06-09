import { Upload } from "lucide-react";
import { StatusChip } from "@/components/ui/status-chip";

export default function PortfolioImportsPage() {
  return (
    <div className="rounded border border-[#2d333d] bg-[#171a20] p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Portfolio Imports</h1>
          <p className="mt-1 text-sm text-[#a0a7b4]">TR-CSV/PDF-Import wird in späteren Phasen an Backend-Jobs gebunden.</p>
        </div>
        <Upload className="text-emerald-300" />
      </div>
      <div className="rounded border border-dashed border-[#4b5563] bg-[#111419] p-8 text-center">
        <StatusChip tone="neutral">Import contract pending</StatusChip>
        <div className="mt-4 text-sm text-[#a0a7b4]">Keine Datei wird im Scaffold verarbeitet.</div>
      </div>
    </div>
  );
}

