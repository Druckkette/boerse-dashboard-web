import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/query-provider";
import { AppShell } from "@/components/ui/app-shell";

export const metadata: Metadata = {
  title: "Börse ohne Bauchgefühl",
  description: "Regelbasierte Trading- und Portfolio-Web-App"
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
