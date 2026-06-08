"use client";

import { PageHeader } from "@/components/common/page-header";
import { LaundryDealList } from "@/components/laundry/laundry-deal-list";
import { useLaundryApprovedDeals } from "@/hooks/use-laundry";

export default function LaundryApprovedPage() {
  const q = useLaundryApprovedDeals(100);
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · APPROVED"
        title="Approved Laundromats"
        subtitle="Opportunities that scored ≥ 75 / 100 with the AI underwriter."
      />
      <LaundryDealList
        deals={q.data ?? []}
        loading={q.isLoading}
        emptyTitle="No approved laundromats yet"
      />
    </div>
  );
}
