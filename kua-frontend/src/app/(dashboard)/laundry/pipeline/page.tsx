"use client";

import { Columns3 } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { LaundryDealList } from "@/components/laundry/laundry-deal-list";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useLaundryApprovedDeals,
  useLaundryManualReview,
  useLaundryRejected,
} from "@/hooks/use-laundry";

export default function LaundryPipelinePage() {
  const approved = useLaundryApprovedDeals(50);
  const review = useLaundryManualReview(50);
  const rejected = useLaundryRejected(50);

  const failed = (rejected.data ?? []).filter(
    (d) => d.deal_status === "rejected" && (d.score ?? 0) < 40,
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · PIPELINE"
        title="Acquisition Pipeline"
        subtitle="Laundry-specific deal pipeline — approved, manual review, rejected and low-score failures."
      />

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>
              <Columns3 className="mr-2 inline h-3.5 w-3.5 text-violet-300" />
              Approved
            </CardTitle>
          </CardHeader>
          <CardContent>
            <LaundryDealList
              deals={(approved.data ?? []).slice(0, 25)}
              loading={approved.isLoading}
              emptyTitle="No approved deals"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <Columns3 className="mr-2 inline h-3.5 w-3.5 text-sky-300" />
              Manual Review
            </CardTitle>
          </CardHeader>
          <CardContent>
            <LaundryDealList
              deals={(review.data ?? []).slice(0, 25)}
              loading={review.isLoading}
              emptyTitle="Manual review queue is empty"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <Columns3 className="mr-2 inline h-3.5 w-3.5 text-rose-300" />
              Rejected
            </CardTitle>
          </CardHeader>
          <CardContent>
            <LaundryDealList
              deals={(rejected.data ?? []).slice(0, 25)}
              loading={rejected.isLoading}
              emptyTitle="Nothing rejected yet"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <Columns3 className="mr-2 inline h-3.5 w-3.5 text-amber-300" />
              Failed / Low score
            </CardTitle>
          </CardHeader>
          <CardContent>
            <LaundryDealList
              deals={failed.slice(0, 25)}
              loading={rejected.isLoading}
              emptyTitle="No failed deals"
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
