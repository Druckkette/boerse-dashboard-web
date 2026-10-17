"use client";

import { useProductUi } from "@/components/ui/ui-mode-provider";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "@/lib/api/client";
import { berlinDate } from "@/lib/date";

export function CreatePositionDialog({ ticker, currency, price, onClose }: { ticker: string; currency: string; price: number; onClose: () => void }) {
  const product=useProductUi();
  const ref = useRef<HTMLDialogElement>(null);
  const client = useQueryClient();
  useEffect(() => { const dialog = ref.current; const overflow=document.body.style.overflow; document.body.style.overflow="hidden"; dialog?.showModal(); return () => {dialog?.close();document.body.style.overflow=overflow;}; }, []);
  const save = useMutation({
    mutationFn: (form: FormData) => api.upsertPortfolioPosition({
      ticker, name: ticker, shares: Number(form.get("shares")), entry_price: Number(form.get("price")),
      currency: String(form.get("currency")), buy_date: String(form.get("date")),
      create_only: true, record_transaction: true, stop_pct: null,
    }),
    onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ["portfolio-snapshot"] }), client.invalidateQueries({ queryKey: ["home-dashboard"] })]); onClose(); }
  });
  return <dialog ref={ref} aria-labelledby="create-position-title" onCancel={event=>{ event.preventDefault(); if(!save.isPending) onClose(); }} className={`${product ? "product-dialog" : ""} m-auto max-h-[94dvh] overflow-y-auto w-[min(480px,94vw)] rounded-xl border border-[#e3e8ef] p-5 backdrop:bg-slate-900/50`}>
    <h2 id="create-position-title" className="text-lg font-semibold">{ticker} · Position anlegen</h2>
    <p className="mt-2 text-sm text-[#687386]">Erfasse eine tatsächlich ausgeführte Transaktion. Eine vorhandene Position wird hier nicht überschrieben.</p>
    <form className="mt-4 grid gap-3" onSubmit={event => { event.preventDefault(); save.mutate(new FormData(event.currentTarget)); }}>
      <label className="text-sm">Stückzahl<input autoFocus className="input-dark mt-1" name="shares" type="number" min="0.00000001" step="any" required /></label>
      <label className="text-sm">Tatsächlicher Einstand<input className="input-dark mt-1" name="price" type="number" min="0.00000001" step="any" defaultValue={price} required /></label>
      <label className="text-sm">Ausführungsdatum<input className="input-dark mt-1" name="date" type="date" defaultValue={berlinDate()} max={berlinDate()} required /></label>
      <label className="text-sm">Ausführungswährung<select className="input-dark mt-1" name="currency" defaultValue={currency}>{["USD", "EUR", "GBP", "CHF", "HKD", "CAD", "JPY", "AUD"].map(value => <option key={value}>{value}</option>)}</select></label>
      {save.error && <p role="alert" className="text-sm text-red-700">{save.error.message}</p>}
      <div className="flex justify-end gap-2"><button type="button" className="app-button" disabled={save.isPending} onClick={onClose}>Abbrechen</button><button type="submit" className="app-button app-button-primary" disabled={save.isPending}>{save.isPending ? "Speichert …" : "Position anlegen"}</button></div>
    </form>
  </dialog>;
}
