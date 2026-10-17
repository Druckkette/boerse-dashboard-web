import type { Metadata } from "next";
import { cookies } from "next/headers";
import { UiModeProvider } from "@/components/ui/ui-mode-provider";
import { connection } from "next/server";
import { isBetaMode } from "@/lib/beta/policy";
import { BetaModeProvider } from "@/components/beta-mode-provider";
import "./globals.css";
import { QueryProvider } from "@/components/query-provider";
import { AppShell } from "@/components/ui/app-shell";

export const metadata: Metadata = {
  title: "Börse ohne Bauchgefühl",
  description: "Regelbasierte Trading- und Portfolio-Web-App"
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  await connection();
  const beta = isBetaMode();
  const mode = (await cookies()).get("dashboard-ui")?.value === "classic" ? "classic" : "product";
  return (
    <html lang="de" data-ui={mode}>
      <body>
        <BetaModeProvider beta={beta}>
          <QueryProvider beta={beta}>
            <UiModeProvider initialMode={mode}><AppShell>{children}</AppShell></UiModeProvider>
          </QueryProvider>
        </BetaModeProvider>
      </body>
    </html>
  );
}
