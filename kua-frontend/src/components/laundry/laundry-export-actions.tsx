"use client";

import * as React from "react";
import { Download, FileSpreadsheet, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { laundryApi, type LaundryPipelineExportScope } from "@/lib/api";
import {
  useCreateLaundryBulkExport,
  useCreateLaundryPipelineExport,
  useCreateLaundryScanExport,
  useCreateLaundryExport,
} from "@/hooks/use-laundry";

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

interface LaundryPipelineExportToolbarProps {
  className?: string;
}

export function LaundryPipelineExportToolbar({ className }: LaundryPipelineExportToolbarProps) {
  const pipelineExport = useCreateLaundryPipelineExport();
  const [lastExport, setLastExport] = React.useState<ExportResult | null>(null);

  async function runScope(scope: LaundryPipelineExportScope, label: string) {
    const toastId = toast.loading(`Exporting ${label}…`);
    try {
      const res = await pipelineExport.mutateAsync(scope);
      setLastExport(res);
      toast.success(`${label} export ready`, {
        id: toastId,
        description: res.filename ?? `${res.row_count ?? 0} properties`,
      });
    } catch (err) {
      toast.error((err as Error).message, { id: toastId });
    }
  }

  const buttons: Array<{ scope: LaundryPipelineExportScope; label: string }> = [
    { scope: "entire", label: "Export pipeline" },
    { scope: "approved", label: "Export approved" },
    { scope: "manual_review", label: "Export review" },
    { scope: "rejected", label: "Export rejected" },
    { scope: "failed", label: "Export failed" },
  ];

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      {buttons.map(({ scope, label }) => (
        <Button
          key={scope}
          type="button"
          variant="ghost"
          size="sm"
          className="h-9 border border-border/60 bg-background/30 font-mono text-[10px] uppercase tracking-widest"
          disabled={pipelineExport.isPending}
          onClick={() => runScope(scope, label)}
        >
          {pipelineExport.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <FileSpreadsheet className="h-3.5 w-3.5" />
          )}
          {label}
        </Button>
      ))}
      {lastExport && (
        <Button
          type="button"
          variant="tactical"
          size="sm"
          className="h-9 bg-violet-500/10 text-violet-200 hover:bg-violet-500/20"
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

export function LaundryPipelineExportMenu({ scanId, className }: LaundryPipelineExportMenuProps) {
  if (!scanId) {
    return <LaundryPipelineExportToolbar className={className} />;
  }

  const scanExport = useCreateLaundryScanExport(scanId);
  const [lastExport, setLastExport] = React.useState<ExportResult | null>(null);

  async function runScanExport() {
    const toastId = toast.loading("Exporting scan…");
    try {
      const res = await scanExport.mutateAsync("entire");
      setLastExport(res);
      toast.success("Scan export ready", { id: toastId });
    } catch (err) {
      toast.error((err as Error).message, { id: toastId });
    }
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <Button
        type="button"
        variant="tactical"
        size="sm"
        className="bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
        disabled={scanExport.isPending}
        onClick={runScanExport}
      >
        {scanExport.isPending ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <FileSpreadsheet className="h-3.5 w-3.5" />
        )}
        Export Excel
      </Button>
      {lastExport && (
        <Button
          type="button"
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
        type="button"
        variant="ghost"
        size="sm"
        className="h-9 border border-border/60 font-mono text-[10px] uppercase tracking-widest"
        disabled={bulkExport.isPending || selectedIds.length === 0}
        onClick={() => runBulk({ property_ids: selectedIds })}
      >
        Export selected
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-9 border border-border/60 font-mono text-[10px] uppercase tracking-widest"
        disabled={bulkExport.isPending}
        onClick={() => runBulk({ scope: "approved" })}
      >
        Export all approved
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-9 border border-border/60 font-mono text-[10px] uppercase tracking-widest"
        disabled={bulkExport.isPending}
        onClick={() => runBulk({ scope: "manual_review" })}
      >
        Export all manual review
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-9 border border-border/60 font-mono text-[10px] uppercase tracking-widest"
        disabled={bulkExport.isPending}
        onClick={() => runBulk({ scope: "entire" })}
      >
        Export entire pipeline
      </Button>
      {lastExport && (
        <Button
          type="button"
          variant="tactical"
          size="sm"
          className="h-9 bg-violet-500/10 text-violet-200 hover:bg-violet-500/20"
          onClick={() => openDownload(lastExport)}
        >
          <Download className="h-3.5 w-3.5" />
          Download Excel
        </Button>
      )}
    </div>
  );
}
