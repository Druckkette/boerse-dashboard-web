"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
export type UiMode = "classic" | "product";
const UiContext = createContext<{
  mode: UiMode;
  changeMode: (mode: UiMode) => void;
}>({ mode: "product", changeMode: () => undefined });
const DraftRegistry = createContext<(id: string, dirty: boolean) => void>(
  () => undefined,
);
const DraftCount = createContext(0);

// Keep draft updates outside the mode context: typing must not remount table editors.
export function UiModeProvider({
  initialMode,
  children,
}: {
  initialMode: UiMode;
  children: ReactNode;
}) {
  const [mode, setMode] = useState(initialMode);
  const draftIds = useRef(new Set<string>());
  const [drafts, setDrafts] = useState(0);
  const registerDraft = useCallback((id: string, dirty: boolean) => {
    if (draftIds.current.has(id) === dirty) return;
    if (dirty) draftIds.current.add(id);
    else draftIds.current.delete(id);
    setDrafts(draftIds.current.size);
  }, []);
  const changeMode = useCallback((next: UiMode) => {
    if (draftIds.current.size) return;
    document.cookie = `dashboard-ui=${next}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
    document.documentElement.dataset.ui = next;
    setMode(next);
  }, []);
  const preference = useMemo(() => ({ mode, changeMode }), [mode, changeMode]);
  return (
    <UiContext.Provider value={preference}>
      <DraftRegistry.Provider value={registerDraft}>
        <DraftCount.Provider value={drafts}>{children}</DraftCount.Provider>
      </DraftRegistry.Provider>
    </UiContext.Provider>
  );
}
export const useUiMode = () => useContext(UiContext);
export const useProductUi = () => useUiMode().mode === "product";
export function useUiDraft(dirty: boolean) {
  const id = useId();
  const registerDraft = useContext(DraftRegistry);
  useEffect(() => {
    registerDraft(id, dirty);
    return () => registerDraft(id, false);
  }, [dirty, id, registerDraft]);
}
export function UiModeSwitch() {
  const { mode, changeMode } = useUiMode();
  const drafts = useContext(DraftCount);
  return (
    <button
      disabled={drafts > 0}
      type="button"
      className="ui-mode-switch rounded-lg border border-[#d8e1ea] bg-white px-3 py-2 text-xs font-semibold text-[#475569] disabled:opacity-50"
      aria-label={
        mode === "product"
          ? "Zur klassischen Ansicht wechseln"
          : "Zur neuen Ansicht wechseln"
      }
      title={
        drafts
          ? "Offene Änderungen zuerst speichern oder verwerfen, dann die Ansicht wechseln."
          : "Nur die Darstellung ändern. Daten und Einstellungen bleiben erhalten."
      }
      onClick={() => changeMode(mode === "product" ? "classic" : "product")}
    >
      {mode === "product" ? "Klassische Ansicht" : "Neue Ansicht"}
    </button>
  );
}
