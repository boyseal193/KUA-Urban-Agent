"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, MapPin, RefreshCcw, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScoreBadge } from "@/components/dashboard/score-badge";
import { DealStatusIndicator } from "@/components/dashboard/deal-status-indicator";
import { YieldWidget } from "@/components/dashboard/yield-widget";

import { ICMemoViewer } from "@/components/deals/ic-memo-viewer";
import { EconomicsTable } from "@/components/deals/economics-table";
import { ScoreBreakdown } from "@/components/deals/score-breakdown";
import { PropertyMetadata } from "@/components/deals/property-metadata";
import { RiskFlags } from "@/components/deals/risk-flags";
import { AiAnalysisTimeline } from "@/components/deals/ai-analysis-timeline";
import { AcquisitionNotes } from "@/components/deals/acquisition-notes";
import { ExportButton } from "@/components/deals/export-button";
import { DealMiniMap } from "@/components/deals/deal-mini-map";
import { KpiGridSkeleton } from "@/components/common/loading-skeleton";
import { EmptyState } from "@/components/common/empty-state";
import {
  DeletePropertyButton,
  purgePropertyCaches,
} from "@/components/properties/delete-property-button";

import { dealKeys, usePropertyDetail } from "@/hooks/use-deals";
import { verdictMeta } from "@/lib/constants";
import { Badge } from "@/components/ui/badge";
import { money, metersLabel } from "@/lib/format";
import { staleProperties } from "@/lib/stale-properties";

export default function DealDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const id = String(params?.id ?? "");
  const { data, isLoading, error, refetch, isRefetching } = usePropertyDetail(id);

  /**
   * If the backend returns "no record" (because the property has been
   * soft-deleted or its id is stale), proactively purge every cache that
   * could still be rendering a card for it. This is the missing piece that
   * makes ghost cards disappear instantly after a delete in another tab.
   */
  const detailMissing =
    !isLoading && !isRefetching && (Boolean(error) || !data?.success || !data?.property);

  React.useEffect(() => {
    if (detailMissing && id) {
      staleProperties.add(id);
      purgePropertyCaches(qc, id);
    }
  }, [detailMissing, id, qc]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="OPS · DEAL DETAIL"
          title="Loading dossier…"
          subtitle="Pulling property record, economics and IC memo."
        />
        <KpiGridSkeleton count={4} />
      </div>
    );
  }

  if (detailMissing) {
    const handleRemoveStaleCard = () => {
      staleProperties.add(id);
      purgePropertyCaches(qc, id);
      toast.success("Stale reference removed", {
        description: "Returning to the pipeline.",
      });
      router.push("/pipeline");
    };

    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="OPS · DEAL DETAIL"
          title="Property no longer available"
          subtitle={
            data?.error?.toString().toLowerCase().includes("deleted")
              ? "This property has been deleted. Any stale cards will be removed."
              : "The property could not be loaded — it may have been deleted or merged."
          }
          rightSlot={
            <Link href="/pipeline">
              <Button variant="outline" size="sm" className="gap-1.5">
                <ArrowLeft className="h-3.5 w-3.5" /> Pipeline
              </Button>
            </Link>
          }
        />
        <EmptyState
          title="No record"
          description="The property record is missing or has been removed. Use the actions below to recover."
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => {
              qc.invalidateQueries({ queryKey: dealKeys.all });
              void refetch();
            }}
          >
            <RefreshCcw className="h-3.5 w-3.5" /> Refresh
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="gap-1.5 text-destructive hover:bg-destructive/[0.08]"
            onClick={handleRemoveStaleCard}
          >
            <Trash2 className="h-3.5 w-3.5" /> Remove stale card
          </Button>
        </div>
      </div>
    );
  }

  if (!data?.property) {
    return null;
  }

  const property = data.property;
  const analysis = data.latest_analysis ?? null;
  const economics = analysis?.economics;
  const score = analysis?.score;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={`OPS · DEAL · ${property.id.slice(0, 8)}`}
        title={property.address || property.neighbourhood || "Untitled asset"}
        subtitle={`${property.neighbourhood ?? "—"} · ${property.city ?? "Barcelona"}`}
        rightSlot={
          <>
            <Link href="/pipeline">
              <Button variant="outline" size="sm" className="gap-1.5">
                <ArrowLeft className="h-3 w-3" /> Pipeline
              </Button>
            </Link>
            <ExportButton property={property} analysis={analysis} />
            <DeletePropertyButton
              propertyId={property.id}
              label={property.address || property.neighbourhood || `Property ${property.id.slice(0, 8)}`}
              redirectTo="/pipeline"
            />
          </>
        }
      />

      {/* Hero strip */}
      <div className="panel-strong relative overflow-hidden p-5 sm:p-6">
        <div className="absolute inset-x-0 top-0 hud-line" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[auto_1fr_auto] lg:items-center">
          <ScoreBadge score={property.score ?? null} size="lg" />

          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <DealStatusIndicator status={property.deal_status ?? null} />
              <Badge className={verdictMeta(property.verdict).chipClass}>
                {verdictMeta(property.verdict).label}
              </Badge>
              <Badge variant="outline">
                {property.classification ?? "—"}
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-sm text-foreground">
              <MapPin className="h-3.5 w-3.5 text-muted-foreground" />
              <span>{property.address ?? "—"}</span>
              <span className="text-muted-foreground">·</span>
              <span>{property.neighbourhood ?? "—"}</span>
            </div>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
              <span>ASKING · <span className="text-foreground">{money(property.asking_price ?? null)}</span></span>
              <span>GBA · <span className="text-foreground">{metersLabel(property.gba_m2 ?? null)}</span></span>
              <span>SOURCE · <span className="text-foreground">{property.source ?? "AUTO"}</span></span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <YieldWidget
              label="True EBITDA Yield"
              value={economics?.true_ebitda_yield ?? null}
            />
            <YieldWidget
              label="EBITDA Yield"
              value={economics?.ebitda_yield ?? null}
            />
          </div>
        </div>
      </div>

      {/* Body */}
      <Tabs defaultValue="memo">
        <TabsList>
          <TabsTrigger value="memo" className="gap-1.5">
            <Sparkles className="h-3 w-3" /> IC Memo
          </TabsTrigger>
          <TabsTrigger value="economics">Economics</TabsTrigger>
          <TabsTrigger value="score">Score</TabsTrigger>
          <TabsTrigger value="metadata">Property</TabsTrigger>
          <TabsTrigger value="map">Map</TabsTrigger>
          <TabsTrigger value="notes">Notes</TabsTrigger>
        </TabsList>

        <TabsContent value="memo">
          <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
            <ICMemoViewer memo={analysis?.ic_memo ?? null} propertyId={property.id} />
            <div className="space-y-4">
              <RiskFlags
                dealKiller={score?.deal_killer ?? null}
                flags={score?.due_diligence_flags ?? []}
              />
              <AiAnalysisTimeline property={property} analysis={analysis} />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="economics">
          <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
            <EconomicsTable economics={economics} />
            <ScoreBreakdown score={score} />
          </div>
        </TabsContent>

        <TabsContent value="score">
          <div className="grid gap-4 lg:grid-cols-[1fr_1.6fr]">
            <ScoreBreakdown score={score} />
            <RiskFlags
              dealKiller={score?.deal_killer ?? null}
              flags={score?.due_diligence_flags ?? []}
            />
          </div>
        </TabsContent>

        <TabsContent value="metadata">
          <PropertyMetadata property={property} />
        </TabsContent>

        <TabsContent value="map">
          <DealMiniMap property={property} />
        </TabsContent>

        <TabsContent value="notes">
          <AcquisitionNotes propertyId={property.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
