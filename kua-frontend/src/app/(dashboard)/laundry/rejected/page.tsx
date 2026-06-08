"use client";

import { PageHeader } from "@/components/common/page-header";
import { LaundryDealList } from "@/components/laundry/laundry-deal-list";
import { useLaundryRejected } from "@/hooks/use-laundry";

export default function LaundryRejectedPage() {
  const q = useLaundryRejected(100);
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · REJECTED"
        title="Rejected Opportunities"
        subtitle="Auto-rejected scores ( < 50 / 100 ). Restore any item to bring it back into the manual-review queue."
      />
      <LaundryDealList
        deals={q.data ?? []}
        loading={q.isLoading}
        emptyTitle="No rejected opportunities"
      />
    </div>
  );
}
