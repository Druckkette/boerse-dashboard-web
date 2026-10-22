import { SettingsPanel } from "@/features/settings/settings-panel";
import { UiModeSwitch } from "@/components/ui/ui-mode-provider";

export default function SettingsPage() {
  return <div className="space-y-4"><section id="darstellung" className="dashboard-section scroll-mt-32"><h2 className="text-lg font-semibold">Darstellung</h2><p className="my-3 text-sm text-[#526174]">Neue oder klassische Oberfläche für diesen Browser wählen. Offene Entwürfe zuerst speichern oder verwerfen.</p><UiModeSwitch/></section><SettingsPanel /></div>;
}
