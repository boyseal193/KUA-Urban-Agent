"use client";

import * as React from "react";
import { Download, FileSpreadsheet, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { laundryApi, type LaundryPipelineExportScope } from "@/lib/api";
import {
  useCreateLaundryBulkExport,
  useCreateLaundryPipelineExport,
  useCreateLaundryScanExport,
  useCreateLaundryExport,
} from "@/hooks/use-laundry";

const PIPELINE_SCOPE_LABELS: Record<LaundryPipelineExportScope, string> = {
  approved: "Approved",
  manual_review: "Manual Review",
  rejected: "Rejected",
  failed: "Failed",
  entire: "Entire Pipeline",
};

interface ExportResult {
  export_id: string;
  filename?: string;
  download_url?: string;
}

function openDownload(result: ExportResult) {
  const url = result.download_url
    ? `/api/proxy${result.download_url}`
    : laundryApi.downloadExportUrl(result.export_id);
  window.open(url, "_blank");
}

interface LaundryExportExcelButtonProps {
  propertyId: string;
  className?: string;
  size?: "sm" | "default";
}

/** Single-deal underwriting workbook export with re-download support. */
export function LaundryExportExcelButton({
  propertyId,
  className,
  size = "sm",
}: LaundryExportExcelButtonProps) {
  const createExport = useCreateLaundryExport(propertyId);
  const [lastExport, setLastExport] = React.useState<ExportResult | null>(null);

  async function runExport() {
    const toastId = toast.loading("Building Excel workbook…");
    try {
      const res = await createExport.mutateAsync("excel");
      setLastExport(res);
      toast.success("Excel export ready", { id: toastId, description: res.filename });
    } catch (err) {
      toast.error((err as Error).message, { id: toastId });
    }
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <Button
        variant="tactical"
        size={size}
        className="bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
        onClick={runExport}
        disabled={createExport.isPending}
      >
        {createExport.isPending ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <FileSpreadsheet className="h-3.5 w-3.5" />
        )}
        Export Excel
      </Button>
      {lastExport && (
        <Button
          variant="ghost"
          size={size}
          className="border border-border/60"
          onClick={() => openDownload(lastExport)}
        >
          <Download className="h-3.5 w-3.5" />
          Download Excel
        </Button>
      )}
    </div>
  );
}

interface LaundryPipelineExportMenuProps {
  scanId?: string;
  className?: string;
}

/** Pipeline or scan-scoped Excel export menu. */
export function LaundryPipelineExportMenu({ scanId, className }: LaundryPipelineExportMenuProps) {
  const pipelineExport = useCreateLaundryPipelineExport();
  const scanExport = useCreateLaundryScanExport(scanId ?? "");
  const mutation = scanId ? scanExport : pipelineExport;
  const [lastExport, setLastExport] = React.useState<ExportResult | null>(null);

  async function runScope(scope: LaundryPipelineExportScope) {
    const toastId = toast.loading(`Exporting ${PIPELINE_SCOPE_LABELS[scope]}…`);
    try {
      const res = scanId
        ? await scanExport.mutateAsync(scope)
        : await pipelineExport.mutateAsync(scope);
      setLastExport(res);
      toast.success("Pipeline export ready", {
        id: toastId,
        description: res.filename ?? `${res.row_count ?? 0} properties`,
      });
    } catch (err) {
      toast.error((err as Error).message, { id: toastId });
    }
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="tactical"
            size="sm"
            className="bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <FileSpreadsheet className="h-3.5 w-3.5" />
            )}
            Export Excel
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          {(Object.keys(PIPELINE_SCOPE_LABELS) as LaundryPipelineExportScope[]).map((scope) => (
            <DropdownMenuItem key={scope} onClick={() => runScope(scope)}>
              {PIPELINE_SCOPE_LABELS[scope]}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      {lastExport && (
        <Button
          variant="ghost"
          size="sm"
          className="border border-border/60"
          onClick={() => openDownload(lastExport)}
        >
          <Download className="h-3.5 w-3.5" />
          Download Excel
        </Button>
      )}
    </div>
  );
}

interface LaundryBulkExportToolbarProps {
  selectedIds?: string[];
  className?: string;
}

/** Bulk export actions for pipeline operators. */
export function LaundryBulkExportToolbar({
  selectedIds = [],
  className,
}: LaundryBulkExportToolbarProps) {
  const bulkExport = useCreateLaundryBulkExport();
  const [lastExport, setLastExport] = React.useState<ExportResult | null>(null);

  async function runBulk(payload: { property_ids?: string[]; scope?: LaundryPipelineExportScope }) {
    const toastId = toast.loading("Building pipeline workbook…");
    try {
      const res = await bulkExport.mutateAsync(payload);
      setLastExport(res);
      toast.success("Bulk export ready", {
        id: toastId,
        description: res.filename ?? `${res.row_count ?? 0} properties`,
      });
    } catch (err) {
      toast.error((err as Error).message, { id: toastId });
    }
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <Button
        variant="ghost"
        size="sm"
        className="border border-border/60"
        disabled={bulkExport.isPending || selectedIds.length === 0}
        onClick={() => runBulk({ property_ids: selectedIds })}
      >
        Export Selected
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="border border-border/60"
        disabled={bulkExport.isPending}
        onClick={() => runBulk({ scope: "approved" })}
      >
        Export All Approved
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="border border-border/60"
        disabled={bulkExport.isPending}
        onClick={() => runBulk({ scope: "manual_review" })}
      >
        Export All Manual Review
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="border border-border/60"
        disabled={bulkExport.isPending}
        onClick={() => runBulk({ scope: "entire" })}
      >
        Export Entire Pipeline
      </Button>
      {lastExport && (
        <Button
          variant="tactical"
          size="sm"
          className="bg-violet-500/10 text-violet-200 hover:bg-violet-500/20"
          onClick={() => openDownload(lastExport)}
        >
          <Download className="h-3.5 w-3.5" />
          Download Excel
        </Button>
      )}
    </div>
  );
}
