"use client";

import { PageHeader } from "@/components/common/page-header";
import { LaundryDealList } from "@/components/laundry/laundry-deal-list";
import { useLaundryManualReview } from "@/hooks/use-laundry";

export default function LaundryManualReviewPage() {
  const q = useLaundryManualReview(100);
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · OPERATOR QUEUE"
        title="Manual Review"
        subtitle="Opportunities awaiting human verification before promotion or rejection."
      />
      <LaundryDealList
        deals={q.data ?? []}
        loading={q.isLoading}
        emptyTitle="Manual review queue is empty"
        emptyDescription="Run a scan to populate the queue."
      />
    </div>
  );
}
