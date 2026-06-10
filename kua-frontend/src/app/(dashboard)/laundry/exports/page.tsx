"use client";

import { Download, FileText } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/common/empty-state";
import { useLaundryExports } from "@/hooks/use-laundry";
import { laundryApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export default function LaundryExportsPage() {
  const q = useLaundryExports(200);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · EXPORTS"
        title="Generated Artefacts"
        subtitle="Professional Excel workbooks generated from the laundry acquisition pipeline."
      />

      <Card>
        <CardHeader>
          <CardTitle>Artefact history</CardTitle>
        </CardHeader>
        <CardContent>
          {q.isLoading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded-md border border-border/60 bg-card/40" />
              ))}
            </div>
          ) : (q.data ?? []).length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No exports yet"
              description="Open a deal and click an export button to generate one."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="border-b border-border/60 text-left font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-2">Type</th>
                    <th className="py-2 pr-2">Label</th>
                    <th className="py-2 pr-2">Format</th>
                    <th className="py-2 pr-2">File</th>
                    <th className="py-2 pr-2">Size</th>
                    <th className="py-2 pr-2">Created</th>
                    <th className="py-2 pr-2">Download</th>
                  </tr>
                </thead>
                <tbody>
                  {(q.data ?? []).map((r) => (
                    <tr key={r.id} className="border-b border-border/40">
                      <td className="py-2 pr-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        {r.export_type ?? r.format}
                      </td>
                      <td className="py-2 pr-2 text-muted-foreground">{r.label ?? "—"}</td>
                      <td className="py-2 pr-2 uppercase tracking-widest font-mono text-[10px]">
                        {r.format}
                      </td>
                      <td className="py-2 pr-2 font-mono text-[10px] text-muted-foreground truncate max-w-[420px]">
                        {r.file_path.split("/").pop()}
                      </td>
                      <td className="py-2 pr-2 font-mono tabular-nums">
                        {(r.size_bytes / 1024).toFixed(1)} KB
                      </td>
                      <td className="py-2 pr-2 text-muted-foreground">{timeAgo(r.created_at)}</td>
                      <td className="py-2 pr-2">
                        <a
                          href={laundryApi.downloadExportUrl(r.id)}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-violet-300 hover:underline"
                        >
                          <Download className="h-3 w-3" /> get
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
