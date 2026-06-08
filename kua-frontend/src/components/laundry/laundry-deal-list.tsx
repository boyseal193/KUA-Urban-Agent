"use client";

import * as React from "react";
import { Inbox } from "lucide-react";

import { EmptyState } from "@/components/common/empty-state";
import { LaundryDealCard } from "./laundry-deal-card";
import type { LaundryProperty } from "@/lib/api";

interface Props {
  deals: LaundryProperty[];
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
}

export function LaundryDealList({
  deals,
  loading,
  emptyTitle = "No deals",
  emptyDescription = "Run a scan to discover laundromat opportunities.",
}: Props) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-xl border border-border/60 bg-card/40"
          />
        ))}
      </div>
    );
  }

  if (!deals.length) {
    return <EmptyState icon={Inbox} title={emptyTitle} description={emptyDescription} />;
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {deals.map((d, i) => (
        <LaundryDealCard key={d.id} deal={d} index={i} />
      ))}
    </div>
  );
}
