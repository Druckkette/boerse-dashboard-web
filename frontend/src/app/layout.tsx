import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/query-provider";
import { AppShell } from "@/components/ui/app-shell";

export const metadata: Metadata = {
  title: "Boerse Dashboard Web",
  description: "API-first trading and portfolio dashboard"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="de">
      <body>
        <QueryProvider>
          <AppShell>{children}</AppShell>
        </QueryProvider>
      </body>
    </html>
  );
}

