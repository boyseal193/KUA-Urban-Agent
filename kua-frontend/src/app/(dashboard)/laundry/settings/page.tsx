"use client";

import * as React from "react";
import { Loader2, Save, Trash2, Wand2 } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/common/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useBulkRescoreLaundry,
  useLaundrySettings,
  usePurgeLaundryTestData,
  useUpdateLaundrySettings,
} from "@/hooks/use-laundry";

export default function LaundrySettingsPage() {
  const q = useLaundrySettings();
  const update = useUpdateLaundrySettings();
  const bulkRescore = useBulkRescoreLaundry();
  const purge = usePurgeLaundryTestData();

  const [json, setJson] = React.useState<string>("{}");
  const [notes, setNotes] = React.useState<string>("");

  React.useEffect(() => {
    if (q.data?.overrides) {
      setJson(JSON.stringify(q.data.overrides, null, 2));
    }
    if (q.data?.notes) {
      setNotes(q.data.notes);
    }
  }, [q.data?.overrides, q.data?.notes]);

  async function onSave() {
    let parsed: Record<string, unknown> = {};
    try {
      parsed = JSON.parse(json || "{}");
    } catch {
      toast.error("Overrides must be valid JSON");
      return;
    }
    await update.mutateAsync({ overrides: parsed, notes });
    toast.success("Saved");
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · SETTINGS"
        title="Engine Settings"
        subtitle="Override the deterministic assumptions used by the laundry underwriter — overrides ripple through every new scan."
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader>
            <CardTitle>Assumption overrides (JSON)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <textarea
              value={json}
              onChange={(e) => setJson(e.target.value)}
              rows={20}
              className="w-full rounded-md border border-border/60 bg-background/40 p-3 font-mono text-[11px] text-foreground focus:outline-none focus:ring-2 focus:ring-violet-400/40"
              spellCheck={false}
            />
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Notes (visible to operators)"
              className="w-full rounded-md border border-border/60 bg-background/40 p-2 font-mono text-xs"
            />
            <Button
              variant="tactical"
              size="sm"
              onClick={onSave}
              disabled={update.isPending}
              className="bg-violet-500/10 text-violet-300 hover:bg-violet-500/20"
            >
              {update.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              Save overrides
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Operations</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start border border-border/60"
              onClick={async () => {
                const out = await bulkRescore.mutateAsync({
                  deal_statuses: ["approved_candidate", "manual_review"],
                  limit: 200,
                });
                toast.success(`Re-scored ${out.count} properties`);
              }}
              disabled={bulkRescore.isPending}
            >
              {bulkRescore.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Wand2 className="h-3.5 w-3.5" />
              )}
              Bulk re-score (approved + review)
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start border border-border/60 text-rose-300 hover:text-rose-200"
              onClick={async () => {
                if (!confirm("Purge all rows flagged source='test' — irreversible. Continue?")) return;
                const out = await purge.mutateAsync();
                toast.success(`Purged ${out.deleted} rows`);
              }}
              disabled={purge.isPending}
            >
              <Trash2 className="h-3.5 w-3.5" /> Purge test data
            </Button>
            <div className="rounded-md border border-border/60 bg-card/40 p-3 font-mono text-[10px] text-muted-foreground">
              <div className="mb-1 uppercase tracking-widest">Effective</div>
              <pre className="max-h-[280px] overflow-auto">
{JSON.stringify(q.data?.effective ?? {}, null, 2)}
              </pre>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
