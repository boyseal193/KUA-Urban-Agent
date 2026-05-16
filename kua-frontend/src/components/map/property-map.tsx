"use client";

/**
 * Cinematic dark Leaflet map with clustered glow markers.
 * Uses CARTO Dark Matter tiles (no API key required) which look gorgeous
 * with our neon overlay theme. Swap to Mapbox by passing NEXT_PUBLIC_MAPBOX_TOKEN
 * and changing the tile URL.
 */

import * as React from "react";
import Link from "next/link";
import L from "leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";
import {
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  ZoomControl,
} from "react-leaflet";

import { BARCELONA_CENTER, dealStatusMeta } from "@/lib/constants";
import { ScoreBadge } from "@/components/dashboard/score-badge";
import { Badge } from "@/components/ui/badge";
import { metersLabel, moneyCompact } from "@/lib/format";
import type { PropertyRecord } from "@/lib/api/types";

interface PropertyMapProps {
  deals: PropertyRecord[];
  height?: number | string;
}

function dealIcon(deal: PropertyRecord) {
  const meta = dealStatusMeta(deal.deal_status);
  const score = Math.round(Number(deal.score) || 0);

  const html = `
    <div class="kua-marker" style="--kua-color:${meta.color}">
      <div class="kua-marker__ring"></div>
      <div class="kua-marker__core">${score}</div>
    </div>
  `;

  return L.divIcon({
    html,
    className: "kua-marker-wrapper",
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });
}

export default function PropertyMap({
  deals,
  height = "calc(100vh - 220px)",
}: PropertyMapProps) {
  const valid = React.useMemo(
    () =>
      deals.filter(
        (d) => typeof d.latitude === "number" && typeof d.longitude === "number"
      ),
    [deals]
  );

  return (
    <div
      className="panel relative overflow-hidden"
      style={{ height }}
    >
      <style jsx global>{`
        .kua-marker-wrapper {
          background: transparent !important;
          border: none !important;
        }
        .kua-marker {
          position: relative;
          width: 40px;
          height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--kua-color);
        }
        .kua-marker__ring {
          position: absolute;
          inset: 0;
          border-radius: 9999px;
          border: 1px solid var(--kua-color);
          box-shadow:
            0 0 12px color-mix(in srgb, var(--kua-color) 60%, transparent),
            inset 0 0 12px color-mix(in srgb, var(--kua-color) 40%, transparent);
          animation: kua-ping 2.4s ease-out infinite;
          opacity: 0.65;
        }
        .kua-marker__core {
          position: relative;
          width: 26px;
          height: 26px;
          border-radius: 9999px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-family: var(--font-mono);
          font-size: 10px;
          font-weight: 600;
          color: #05070a;
          background: var(--kua-color);
          box-shadow:
            0 0 14px color-mix(in srgb, var(--kua-color) 70%, transparent);
        }
        @keyframes kua-ping {
          0% { transform: scale(0.9); opacity: 0.85; }
          70% { transform: scale(1.6); opacity: 0; }
          100% { transform: scale(1.6); opacity: 0; }
        }
      `}</style>

      <MapContainer
        center={BARCELONA_CENTER}
        zoom={13}
        zoomControl={false}
        scrollWheelZoom
        style={{ width: "100%", height: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png"
          subdomains={["a", "b", "c", "d"]}
        />
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png"
          subdomains={["a", "b", "c", "d"]}
          opacity={0.75}
        />
        <ZoomControl position="bottomright" />

        <MarkerClusterGroup chunkedLoading maxClusterRadius={48}>
          {valid.map((d) => (
            <Marker
              key={d.id}
              position={[d.latitude as number, d.longitude as number]}
              icon={dealIcon(d)}
            >
              <Popup>
                <PopupContent deal={d} />
              </Popup>
            </Marker>
          ))}
        </MarkerClusterGroup>
      </MapContainer>

      <div className="pointer-events-none absolute left-3 top-3 z-[400] flex flex-col gap-1">
        <div className="rounded-md border border-border/60 bg-card/80 px-3 py-2 backdrop-blur-xl">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Sector
          </div>
          <div className="font-display text-sm font-semibold text-foreground">
            Barcelona · Greater Metropolitan
          </div>
        </div>
        <Legend />
      </div>
    </div>
  );
}

function Legend() {
  const items = [
    { c: "#7CFAB3", label: "Approved" },
    { c: "#F5B400", label: "Manual review" },
    { c: "#FF4D6D", label: "Rejected" },
  ];
  return (
    <div className="rounded-md border border-border/60 bg-card/80 px-3 py-2 backdrop-blur-xl">
      <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        Legend
      </div>
      <div className="space-y-0.5">
        {items.map((i) => (
          <div
            key={i.label}
            className="flex items-center gap-1.5 font-mono text-[10px] text-foreground/80"
          >
            <span
              className="badge-dot"
              style={{ backgroundColor: i.c, boxShadow: `0 0 6px ${i.c}` }}
            />
            {i.label}
          </div>
        ))}
      </div>
    </div>
  );
}

function PopupContent({ deal }: { deal: PropertyRecord }) {
  const meta = dealStatusMeta(deal.deal_status);
  return (
    <div className="min-w-[220px] space-y-2">
      <div className="flex items-center justify-between">
        <ScoreBadge score={deal.score ?? null} size="sm" showTier={false} />
        <Badge className={meta.chipClass}>{meta.short}</Badge>
      </div>
      <div>
        <div className="text-xs font-semibold text-foreground">
          {deal.address || deal.neighbourhood || "—"}
        </div>
        <div className="text-[10px] text-muted-foreground">
          {deal.neighbourhood || "—"} · {deal.city || "Barcelona"}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 font-mono text-[11px] tabular-nums">
        <div>
          <div className="tactical-mono">Asking</div>
          <div className="text-foreground">
            {moneyCompact(deal.asking_price ?? null)}
          </div>
        </div>
        <div>
          <div className="tactical-mono">GBA</div>
          <div className="text-foreground">
            {metersLabel(deal.gba_m2 ?? null)}
          </div>
        </div>
      </div>
      <Link
        href={`/deals/${deal.id}`}
        className="block rounded-md border border-primary/30 bg-primary/10 px-2.5 py-1.5 text-center font-mono text-[10px] uppercase tracking-widest text-primary hover:bg-primary/20"
      >
        Open memo
      </Link>
    </div>
  );
}
