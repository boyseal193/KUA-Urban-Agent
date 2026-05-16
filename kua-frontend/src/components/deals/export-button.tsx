"use client";

import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import type { AnalysisRecord, PropertyRecord } from "@/lib/api/types";

interface ExportButtonProps {
  property: PropertyRecord;
  analysis?: AnalysisRecord | null;
}

export function ExportButton({ property, analysis }: ExportButtonProps) {
  function handleExport() {
    const payload = {
      property,
      analysis,
      exportedAt: new Date().toISOString(),
      exportedBy: "K.U.A.",
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `kua-deal-${property.id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success("Deal exported", {
      description: "JSON snapshot saved locally. Excel exports are produced during scans.",
    });
  }

  return (
    <Button
      onClick={handleExport}
      variant="tactical"
      size="sm"
      className="gap-1.5"
    >
      <Download className="h-3.5 w-3.5" /> Export deal
    </Button>
  );
}
