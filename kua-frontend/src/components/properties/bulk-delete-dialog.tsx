"use client";

import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { ApiError } from "@/lib/api/client";
import {
  BULK_DELETE_CONFIRMATION_REQUIRED_AT,
  BULK_DELETE_HARD_LIMIT,
  BULK_DELETE_TYPED_CONFIRMATION,
  propertiesApi,
  type BulkDeleteResult,
} from "@/lib/api/properties";
import { staleProperties } from "@/lib/stale-properties";
import { dealKeys } from "@/hooks/use-deals";

interface BulkDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  propertyIds: string[];
  /** Free-form label shown above the count, e.g. "Test properties". */
  category?: string;
  /** Reason recorded in the audit log. */
  reason?: string;
  /** Optional list of human-readable rows for the preview. */
  previewRows?: Array<{ id: string; label?: string | null }>;
  onCompleted?: (result: BulkDeleteResult) => void;
}

/**
 * Typed-confirmation bulk-delete dialog. Enforces the same safety guards
 * the backend enforces (max 100 ids per batch, "DELETE" confirmation when
 * deleting ≥10 items) so the operator can never accidentally trigger a
 * mass-deletion with a single misclick.
 */
export function BulkDeleteDialog({
  open,
  onOpenChange,
  propertyIds,
  category,
  reason,
  previewRows,
  onCompleted,
}: BulkDeleteDialogProps) {
  const qc = useQueryClient();
  const [typed, setTyped] = React.useState("");
  const [running, setRunning] = React.useState(false);

  // Deduplicate + trim defensively so the count we show matches what the
  // backend will actually process.
  const ids = React.useMemo(
    () => Array.from(new Set(propertyIds.filter(Boolean))),
    [propertyIds]
  );

  React.useEffect(() => {
    if (!open) setTyped("");
  }, [open]);

  const needsTypedConfirmation =
    ids.length >= BULK_DELETE_CONFIRMATION_REQUIRED_AT;
  const exceedsHardLimit = ids.length > BULK_DELETE_HARD_LIMIT;
  const typedOk = !needsTypedConfirmation || typed === BULK_DELETE_TYPED_CONFIRMATION;
  const canConfirm = !running && ids.length > 0 && typedOk && !exceedsHardLimit;

  const handleConfirm = async () => {
    if (!canConfirm) return;
    setRunning(true);
    try {
      const res = await propertiesApi.bulkDelete(ids, {
        reason: reason ?? category ?? "bulk_delete",
        confirmation: needsTypedConfirmation ? BULK_DELETE_TYPED_CONFIRMATION : undefined,
      });

      if (!res.success) {
        toast.error("Bulk delete blocked", {
          description: res.message ?? res.error ?? "The backend rejected the request.",
        });
        onCompleted?.(res);
        return;
      }

      // Pre-emptively mark every targeted id as stale so cards vanish
      // even before React-Query refetches.
      staleProperties.addMany(ids);

      qc.invalidateQueries({ queryKey: dealKeys.all });
      qc.invalidateQueries({ queryKey: ["scan-history-full"] });
      qc.invalidateQueries({ queryKey: ["deleted-properties"] });
      qc.invalidateQueries({ queryKey: ["admin-stats"] });
      qc.invalidateQueries({ queryKey: ["admin-duplicates"] });
      qc.invalidateQueries({ queryKey: ["pipeline"] });
      qc.invalidateQueries({ queryKey: ["map-properties"] });

      const errCount = res.errors?.length ?? 0;
      toast.success(
        errCount === 0
          ? `${res.deleted} properties deleted`
          : `${res.deleted} deleted, ${errCount} failed`,
        {
          description: category
            ? `Category: ${category}`
            : "Bulk delete completed.",
        }
      );
      onCompleted?.(res);
      onOpenChange(false);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error)?.message;
      toast.error("Bulk delete failed", { description: msg });
    } finally {
      setRunning(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-destructive/40 bg-destructive/[0.08]">
              <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
            </span>
            Bulk delete properties?
          </DialogTitle>
          <DialogDescription>
            {category ? (
              <>
                You are about to soft-delete{" "}
                <span className="font-medium text-foreground">{ids.length}</span>{" "}
                {category}.
              </>
            ) : (
              <>
                You are about to soft-delete{" "}
                <span className="font-medium text-foreground">{ids.length}</span>{" "}
                properties.
              </>
            )}{" "}
            They will disappear from every pipeline, dashboard and export. Memos
            and analyses for these properties will be hidden too. You can
            restore individual properties from the audit log if needed.
          </DialogDescription>
        </DialogHeader>

        {/* Preview */}
        {previewRows && previewRows.length > 0 && (
          <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-border/60 bg-white/[0.02] p-2">
            {previewRows.slice(0, 12).map((r) => (
              <div
                key={r.id}
                className="flex items-center gap-2 text-[11px] text-muted-foreground"
              >
                <span className="font-mono text-[10px] text-muted-foreground/70">
                  {r.id.slice(0, 8)}
                </span>
                <span className="truncate text-foreground/80">
                  {r.label ?? "—"}
                </span>
              </div>
            ))}
            {previewRows.length > 12 && (
              <div className="pt-1 text-[10px] uppercase tracking-widest text-muted-foreground">
                + {previewRows.length - 12} more
              </div>
            )}
          </div>
        )}

        {/* Server-enforced limit warning */}
        {exceedsHardLimit && (
          <div className="rounded-md border border-destructive/40 bg-destructive/[0.06] px-3 py-2 text-[11px] text-destructive">
            This batch contains <strong>{ids.length}</strong> ids, which exceeds
            the server limit of <strong>{BULK_DELETE_HARD_LIMIT}</strong>. Split
            into smaller batches or refine your filters.
          </div>
        )}

        {/* Typed confirmation */}
        {needsTypedConfirmation && !exceedsHardLimit && (
          <div className="space-y-2 rounded-md border border-border/60 bg-white/[0.02] p-3">
            <Label
              htmlFor="bulk-delete-typed"
              className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground"
            >
              Type{" "}
              <code className="rounded bg-destructive/[0.08] px-1 font-mono text-destructive">
                {BULK_DELETE_TYPED_CONFIRMATION}
              </code>{" "}
              to confirm
            </Label>
            <Input
              id="bulk-delete-typed"
              value={typed}
              onChange={(e) => setTyped(e.target.value.trim())}
              placeholder={BULK_DELETE_TYPED_CONFIRMATION}
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              disabled={running}
            />
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Typed confirmation is required for batches of{" "}
              {BULK_DELETE_CONFIRMATION_REQUIRED_AT}+ items.
            </p>
          </div>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={running}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={!canConfirm}
            className="gap-2 bg-destructive/90 text-destructive-foreground hover:bg-destructive"
          >
            {running ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
            Delete {ids.length || ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
