"use client";

import * as React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";

import { DealStatusIndicator } from "./deal-status-indicator";
import { ScoreBadge } from "./score-badge";
import { money, metersLabel } from "@/lib/format";
import { verdictMeta } from "@/lib/constants";
import { Badge } from "@/components/ui/badge";
import { useStaleProperties } from "@/lib/stale-properties";
import type { PropertyRecord } from "@/lib/api/types";

interface DealTableProps {
  deals: PropertyRecord[];
}

export function DealTable({ deals: incomingDeals }: DealTableProps) {
  const { isStale } = useStaleProperties();
  const deals = React.useMemo(
    () =>
      Array.isArray(incomingDeals)
        ? incomingDeals.filter((d) => d && !isStale(d.id))
        : [],
    [incomingDeals, isStale]
  );
  return (
    <div className="panel overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[920px] text-sm">
          <thead>
            <tr className="border-b border-border/60 bg-white/[0.02]">
              <Th>Score</Th>
              <Th>Address</Th>
              <Th>District</Th>
              <Th>Verdict</Th>
              <Th>Status</Th>
              <Th align="right">Asking</Th>
              <Th align="right">GBA</Th>
              <Th align="right">€/m²</Th>
              <Th align="right" />
            </tr>
          </thead>
          <tbody>
            {deals.map((d, i) => {
              const verdict = verdictMeta(d.verdict);
              const ppm =
                d.asking_price && d.gba_m2 ? d.asking_price / d.gba_m2 : null;
              return (
                <motion.tr
                  key={d.id}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.02, 0.4) }}
                  className="group border-b border-border/40 transition-colors hover:bg-primary/[0.04]"
                >
                  <Td>
                    <ScoreBadge score={d.score ?? null} size="sm" showTier={false} />
                  </Td>
                  <Td>
                    <Link
                      href={`/deals/${d.id}`}
                      className="font-medium text-foreground hover:text-primary"
                    >
                      {d.address || "—"}
                    </Link>
                  </Td>
                  <Td>
                    <span className="text-muted-foreground">
                      {d.neighbourhood || "—"}
                    </span>
                  </Td>
                  <Td>
                    <Badge className={verdict.chipClass}>{verdict.label}</Badge>
                  </Td>
                  <Td>
                    <DealStatusIndicator status={d.deal_status ?? null} />
                  </Td>
                  <Td align="right">
                    <span className="font-mono tabular-nums">
                      {money(d.asking_price ?? null)}
                    </span>
                  </Td>
                  <Td align="right">
                    <span className="font-mono tabular-nums">
                      {metersLabel(d.gba_m2 ?? null)}
                    </span>
                  </Td>
                  <Td align="right">
                    <span className="font-mono tabular-nums text-muted-foreground">
                      {ppm ? `€${ppm.toFixed(0)}` : "—"}
                    </span>
                  </Td>
                  <Td align="right">
                    <Link
                      href={`/deals/${d.id}`}
                      className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-primary opacity-0 transition-opacity group-hover:opacity-100"
                    >
                      OPEN <ArrowUpRight className="h-3 w-3" />
                    </Link>
                  </Td>
                </motion.tr>
              );
            })}
            {deals.length === 0 && (
              <tr>
                <Td colSpan={9} align="center">
                  <span className="text-muted-foreground">No deals.</span>
                </Td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Th({
  children,
  align = "left",
}: {
  children?: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      className={`px-4 py-2.5 text-${align} font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align = "left",
  colSpan,
}: {
  children?: React.ReactNode;
  align?: "left" | "right" | "center";
  colSpan?: number;
}) {
  return (
    <td className={`px-4 py-3 text-${align}`} colSpan={colSpan}>
      {children}
    </td>
  );
}
