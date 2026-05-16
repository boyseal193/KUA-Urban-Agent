"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { scanApi } from "@/lib/api/scan";
import { dealKeys } from "./use-deals";
import type { AutoScanFilters, ScanResponse } from "@/lib/api/types";

/**
 * Scan launcher hook.
 *
 * The backend currently returns the full batch synchronously when the scan
 * finishes. To preserve the "live ingestion feel" specified in the brief,
 * we expose a `progress` state machine that animates the in-flight phase
 * (pending → scraping → analysing → done) while the network call resolves.
 */
export type ScanPhase =
  | "idle"
  | "queued"
  | "scraping"
  | "analysing"
  | "scoring"
  | "complete"
  | "error";

export function useAutoScan() {
  const qc = useQueryClient();
  const [phase, setPhase] = React.useState<ScanPhase>("idle");
  const [progress, setProgress] = React.useState(0);
  const timersRef = React.useRef<ReturnType<typeof setTimeout>[]>([]);

  React.useEffect(
    () => () => timersRef.current.forEach(clearTimeout),
    []
  );

  const mutation = useMutation<ScanResponse, Error, AutoScanFilters>({
    mutationFn: async (filters) => {
      setPhase("queued");
      setProgress(8);

      timersRef.current.push(
        setTimeout(() => {
          setPhase("scraping");
          setProgress(24);
        }, 380)
      );
      timersRef.current.push(
        setTimeout(() => {
          setPhase("analysing");
          setProgress(58);
        }, 1400)
      );
      timersRef.current.push(
        setTimeout(() => {
          setPhase("scoring");
          setProgress(82);
        }, 2600)
      );

      const data = await scanApi.auto(filters);
      timersRef.current.forEach(clearTimeout);
      setPhase("complete");
      setProgress(100);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: dealKeys.all });
    },
    onError: () => {
      setPhase("error");
    },
  });

  const reset = React.useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    setPhase("idle");
    setProgress(0);
    mutation.reset();
  }, [mutation]);

  return { ...mutation, phase, progress, reset };
}

export function useAnalyseSingle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { url?: string; raw_text?: string }) =>
      scanApi.analyse(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: dealKeys.all });
    },
  });
}
