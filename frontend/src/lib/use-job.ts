"use client";
import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

export const terminalJobStatuses = new Set(["done", "failed", "skipped", "cancelled"]);

export function useJob(jobId: string | null, invalidations: string[]) {
  const client = useQueryClient();
  const signature = invalidations.join(",");
  const query = useQuery({ queryKey: ["job-progress", jobId], queryFn: () => api.jobProgress(jobId!), enabled: Boolean(jobId),
    refetchInterval: state => state.state.data && terminalJobStatuses.has(state.state.data.status) ? false : 1500 });
  const status = query.data?.status;
  useEffect(() => {
    if (status === "done" || status === "skipped") for (const key of signature.split(",")) void client.invalidateQueries({ queryKey: [key] });
  }, [status, client, signature]);
  return { ...query, running: Boolean(jobId && (!status || !terminalJobStatuses.has(status))) };
}
