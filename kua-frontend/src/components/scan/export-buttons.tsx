"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Archive,
  Download,
  FileJson,
  FileSpreadsheet,
  FileText,
  Loader2,
  RefreshCcw,
  Sheet,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ApiError,
  EXPORT_FORMAT_META,
  downloadExport,
  regenerateExports,
  type ExportFormat,
} from "@/lib/api";

const FORMAT_ICONS: Record<ExportFormat, React.ComponentType<{ className?: string }>> = {
  excel: FileSpreadsheet,
  csv: Sheet,
  json: FileJson,
  memo: FileText,
  zip: Archive,
};

const DEFAULT_ORDER: ExportFormat[] = ["excel", "csv", "json", "memo", "zip"];

interface ExportButtonsProps {
  jobId: string | null | undefined;
  formats?: ExportFormat[];
  /** Disable everything (e.g. scan not finished yet). */
  disabled?: boolean;
  /** Compact = icon buttons in a row. Default lays them out in a grid. */
  variant?: "default" | "compact";
  /** Show the regenerate button. */
  showRegenerate?: boolean;
  className?: string;
}

export function ExportButtons({
  jobId,
  formats = DEFAULT_ORDER,
  disabled = false,
  variant = "default",
  showRegenerate = true,
  className,
}: ExportButtonsProps) {
  const [busy, setBusy] = React.useState<Record<ExportFormat, boolean>>({
    excel: false,
    csv: false,
    json: false,
    memo: false,
    zip: false,
  });
  const [regenerating, setRegenerating] = React.useState(false);

  const cleanlyDisabled = disabled || !jobId;

  const runDownload = React.useCallback(
    async (fmt: ExportFormat) => {
      if (!jobId || busy[fmt]) return;
      setBusy((b) => ({ ...b, [fmt]: true }));
      const meta = EXPORT_FORMAT_META[fmt];
      const toastId = toast.loading(`Preparing ${meta.label}…`, {
        description: "Generating from latest scan data.",
      });
      try {
        const { filename } = await downloadExport(jobId, fmt);
        toast.success(`Downloaded ${meta.label}`, {
          id: toastId,
          description: filename,
        });
      } catch (err: unknown) {
        const message =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
            ? err.message
            : "Download failed";
        toast.error(`${meta.label} export failed`, {
          id: toastId,
          description: message,
          duration: 8_000,
        });
      } finally {
        setBusy((b) => ({ ...b, [fmt]: false }));
      }
    },
    [jobId, busy]
  );

  const runRegenerate = React.useCallback(async () => {
    if (!jobId) return;
    setRegenerating(true);
    const toastId = toast.loading("Regenerating all exports…", {
      description: "Worker is rebuilding artifacts from the latest data.",
    });
    try {
      const res = await regenerateExports(jobId);
      const ok = Object.values(res.outcome).filter(Boolean).length;
      const total = Object.keys(res.outcome).length;
      toast.success("Exports regenerated", {
        id: toastId,
        description: `${ok}/${total} artifacts refreshed.`,
      });
    } catch (err: unknown) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
          ? err.message
          : "Regeneration failed";
      toast.error("Regeneration failed", {
        id: toastId,
        description: message,
        duration: 8_000,
      });
    } finally {
      setRegenerating(false);
    }
  }, [jobId]);

  if (variant === "compact") {
    return (
      <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
        {formats.map((fmt) => {
          const Icon = FORMAT_ICONS[fmt];
          const meta = EXPORT_FORMAT_META[fmt];
          const isBusy = busy[fmt];
          return (
            <Button
              key={fmt}
              size="sm"
              variant="ghost"
              type="button"
              disabled={cleanlyDisabled || isBusy}
              onClick={() => runDownload(fmt)}
              title={meta.description}
              aria-label={`Download ${meta.label}`}
              className="gap-1.5 px-2.5"
            >
              {isBusy ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Icon className="h-3 w-3" />
              )}
              <span className="text-[10px] font-mono uppercase tracking-widest">
                {fmt === "memo" ? "Memo" : fmt}
              </span>
            </Button>
          );
        })}
        {showRegenerate && (
          <Button
            size="sm"
            variant="ghost"
            type="button"
            disabled={cleanlyDisabled || regenerating}
            onClick={runRegenerate}
            title="Force regenerate all export artifacts"
            aria-label="Regenerate exports"
            className="gap-1.5 px-2.5"
          >
            {regenerating ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RefreshCcw className="h-3 w-3" />
            )}
            <span className="text-[10px] font-mono uppercase tracking-widest">
              Refresh
            </span>
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Download className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">Export package</h3>
        </div>
        {showRegenerate && (
          <Button
            size="sm"
            variant="ghost"
            type="button"
            disabled={cleanlyDisabled || regenerating}
            onClick={runRegenerate}
            className="gap-1.5"
            title="Force regenerate every export artifact"
          >
            {regenerating ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RefreshCcw className="h-3 w-3" />
            )}
            <span className="text-[10px] font-mono uppercase tracking-widest">
              Regenerate
            </span>
          </Button>
        )}
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {formats.map((fmt) => {
          const Icon = FORMAT_ICONS[fmt];
          const meta = EXPORT_FORMAT_META[fmt];
          const isBusy = busy[fmt];
          return (
            <Button
              key={fmt}
              type="button"
              variant="outline"
              size="lg"
              disabled={cleanlyDisabled || isBusy}
              onClick={() => runDownload(fmt)}
              className={cn(
                "h-auto justify-start gap-3 border-border/60 bg-card/40 px-3 py-3 text-left",
                "hover:border-primary/50 hover:bg-primary/[0.04]",
                "transition-colors"
              )}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-primary/30 bg-primary/10 text-primary">
                {isBusy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Icon className="h-4 w-4" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-foreground">
                  {meta.label}
                </div>
                <div className="truncate text-[10px] text-muted-foreground">
                  {meta.description}
                </div>
              </div>
            </Button>
          );
        })}
      </div>
      {cleanlyDisabled && (
        <p className="text-[10px] text-muted-foreground">
          Exports unlock when a scan completes successfully.
        </p>
      )}
    </div>
  );
}
