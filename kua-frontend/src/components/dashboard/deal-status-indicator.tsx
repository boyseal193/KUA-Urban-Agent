"use client";

import { Badge } from "@/components/ui/badge";
import { dealStatusMeta } from "@/lib/constants";
import type { DealStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface DealStatusIndicatorProps {
  status?: DealStatus | null;
  className?: string;
  showDot?: boolean;
}

export function DealStatusIndicator({
  status,
  className,
  showDot = true,
}: DealStatusIndicatorProps) {
  const meta = dealStatusMeta(status);
  return (
    <Badge className={cn(meta.chipClass, className)}>
      {showDot && (
        <span
          className="badge-dot"
          style={{ backgroundColor: meta.color, boxShadow: `0 0 6px ${meta.color}` }}
        />
      )}
      {meta.short}
    </Badge>
  );
}
