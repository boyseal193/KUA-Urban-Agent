"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Loader2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { propertiesApi } from "@/lib/api/properties";
import { ApiError } from "@/lib/api/client";
import { dealKeys } from "@/hooks/use-deals";
import { staleProperties } from "@/lib/stale-properties";
import { cn } from "@/lib/utils";

/**
 * Invalidate (and where relevant, remove) every cache that could still
 * contain a reference to a deleted property — so the UI never renders a
 * card or detail-page link that resolves to "Property not found".
 */
function purgePropertyCaches(qc: ReturnType<typeof useQueryClient>, propertyId: string) {
  staleProperties.add(propertyId);

  qc.invalidateQueries({ queryKey: dealKeys.all });
  qc.invalidateQueries({ queryKey: ["scan-job"] });
  qc.invalidateQueries({ queryKey: ["scan-history"] });
  qc.invalidateQueries({ queryKey: ["scan-history-full"] });
  qc.invalidateQueries({ queryKey: ["jobs-list"] });
  qc.invalidateQueries({ queryKey: ["deleted-properties"] });
  qc.invalidateQueries({ queryKey: ["admin-stats"] });
  qc.invalidateQueries({ queryKey: ["admin-duplicates"] });
  qc.invalidateQueries({ queryKey: ["pipeline"] });
  qc.invalidateQueries({ queryKey: ["map-properties"] });

  qc.removeQueries({ queryKey: dealKeys.detail(propertyId) });
  qc.removeQueries({ queryKey: ["property", propertyId] });
}

function restorePropertyCaches(qc: ReturnType<typeof useQueryClient>, propertyId: string) {
  staleProperties.remove(propertyId);
  qc.invalidateQueries({ queryKey: dealKeys.all });
  qc.invalidateQueries({ queryKey: ["scan-history-full"] });
  qc.invalidateQueries({ queryKey: ["deleted-properties"] });
  qc.invalidateQueries({ queryKey: ["admin-stats"] });
  qc.invalidateQueries({ queryKey: ["pipeline"] });
  qc.invalidateQueries({ queryKey: ["map-properties"] });
}

export { purgePropertyCaches, restorePropertyCaches };

interface DeletePropertyButtonProps {
  propertyId: string;
  /** Optional label to show in the toast / dialog ("Carrer del Carme 10"). */
  label?: string | null;
  /** When provided, the user is redirected here after a successful delete. */
  redirectTo?: string;
  variant?: "icon" | "button";
  size?: "sm" | "md";
  className?: string;
  /** Allows the parent to react (e.g. close a drawer). */
  onDeleted?: (id: string) => void;
}

export function DeletePropertyButton({
  propertyId,
  label,
  redirectTo,
  variant = "button",
  size = "sm",
  className,
  onDeleted,
}: DeletePropertyButtonProps) {
  const qc = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState("");

  const mutation = useMutation({
    mutationFn: (r?: string) => propertiesApi.delete(propertyId, r),
    onSuccess: (res) => {
      if (!res.success) {
        toast.error("Delete failed", { description: res.error ?? "unknown error" });
        return;
      }

      purgePropertyCaches(qc, propertyId);

      toast.success("Property deleted", {
        description: label
          ? `"${label}" has been removed from active deals.`
          : `Property ${propertyId.slice(0, 8)} removed.`,
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              const r = await propertiesApi.restore(propertyId);
              if (r.success) {
                restorePropertyCaches(qc, propertyId);
                toast.success("Property restored");
              } else {
                toast.error("Restore failed", { description: r.error ?? "unknown" });
              }
            } catch (e) {
              const msg = e instanceof ApiError ? e.message : (e as Error)?.message;
              toast.error("Restore failed", { description: msg });
            }
          },
        },
      });

      setOpen(false);
      onDeleted?.(propertyId);
      if (redirectTo) router.push(redirectTo);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof ApiError ? err.message : (err as Error)?.message ?? "Unknown error";
      toast.error("Delete failed", { description: msg });
    },
  });

  const handleConfirm = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    mutation.mutate(reason.trim() || undefined);
  };

  const stopBubble = (e: React.MouseEvent) => {
    // Prevent the surrounding card's <Link> from navigating when the
    // operator opens / interacts with the dialog.
    e.stopPropagation();
  };

  const isPending = mutation.isPending;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {variant === "icon" ? (
          <button
            type="button"
            onClick={stopBubble}
            disabled={isPending}
            aria-label="Delete property"
            className={cn(
              "inline-flex h-7 w-7 items-center justify-center rounded-md border border-border/60 bg-card/60 text-muted-foreground transition",
              "hover:border-destructive/40 hover:bg-destructive/[0.08] hover:text-destructive",
              "disabled:cursor-not-allowed disabled:opacity-60",
              className
            )}
          >
            {isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
          </button>
        ) : (
          <Button
            type="button"
            variant="ghost"
            size={size === "sm" ? "sm" : "default"}
            onClick={stopBubble}
            disabled={isPending}
            className={cn(
              "gap-1.5 text-muted-foreground hover:border-destructive/40 hover:bg-destructive/[0.08] hover:text-destructive",
              className
            )}
          >
            {isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Trash2 className="h-3 w-3" />
            )}
            Delete
          </Button>
        )}
      </DialogTrigger>
      <DialogContent
        onClick={stopBubble}
        className="max-w-md"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-destructive/40 bg-destructive/[0.08]">
              <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
            </span>
            Delete property?
          </DialogTitle>
          <DialogDescription>
            {label ? (
              <>
                <span className="font-medium text-foreground">{label}</span> will be
                removed from active pipelines, dashboards, exports and the map. Its
                memos and analyses will be hidden too.
              </>
            ) : (
              "This property will be removed from active pipelines, dashboards, exports and the map."
            )}
            <br />
            You can restore it within the audit log if you change your mind.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Label
            htmlFor={`delete-reason-${propertyId}`}
            className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground"
          >
            Reason (optional)
          </Label>
          <Input
            id={`delete-reason-${propertyId}`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="duplicate / bad data / test record / …"
            disabled={isPending}
          />
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => setOpen(false)}
            disabled={isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={isPending}
            className="gap-2 bg-destructive/90 text-destructive-foreground hover:bg-destructive"
          >
            {isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
            Confirm delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
