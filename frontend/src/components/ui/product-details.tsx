"use client";
import type { ReactNode } from "react";
import { useProductUi } from "./ui-mode-provider";
export function ProductDetails({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const product = useProductUi();
  return product ? (
    <details className="dashboard-section">
      <summary className="cursor-pointer py-2 text-sm font-semibold">
        {title}
      </summary>
      <div className="mt-3 space-y-4">{children}</div>
    </details>
  ) : (
    <>{children}</>
  );
}
