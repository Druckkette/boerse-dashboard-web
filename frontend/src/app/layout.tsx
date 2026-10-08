import type { Metadata } from "next";
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
  return (
    <html lang="de">
      <body>
        <BetaModeProvider beta={beta}>
          <QueryProvider beta={beta}>
            <AppShell>{children}</AppShell>
          </QueryProvider>
        </BetaModeProvider>
      </body>
    </html>
  );
}
