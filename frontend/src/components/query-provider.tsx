"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactNode, useState } from "react";

export function QueryProvider({ children, beta = false }: { children: ReactNode; beta?: boolean }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: beta ? 60_000 : 30_000,
            refetchInterval: false,
            refetchOnWindowFocus: !beta,
            refetchOnReconnect: true,
            retry: beta ? false : 1
          }
        }
      })
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
