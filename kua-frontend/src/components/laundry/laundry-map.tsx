"use client";

import * as React from "react";
import Link from "next/link";
import L from "leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";
import { MapContainer, Marker, Popup, TileLayer, ZoomControl } from "react-leaflet";

import { BARCELONA_CENTER } from "@/lib/constants";
import { laundryStatusMeta } from "./laundry-status";
import { laundryTier } from "./laundry-score-badge";
import type { LaundryMapMarker } from "@/lib/api";

interface Props {
  markers: LaundryMapMarker[];
  height?: number | string;
  missingCount?: number;
  totalCount?: number;
}

function buildIcon(score: number | null, color: string) {
  const safe = Math.round(Number(score) || 0);
  const html = `
    <div class="kua-marker" style="--kua-color:${color}">
      <div class="kua-marker__ring"></div>
      <div class="kua-marker__core">${safe}</div>
    </div>
  `;
  return L.divIcon({
    html,
    className: "kua-marker-wrapper",
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });
}

export default function LaundryMap({
  markers,
  height = "calc(100vh - 220px)",
  missingCount = 0,
  totalCount,
}: Props) {
  const valid = React.useMemo(
    () =>
      markers.filter(
        (m) => typeof m.lat === "number" && typeof m.lng === "number",
      ),
    [markers],
  );

  return (
    <div className="panel relative overflow-hidden" style={{ height }}>
      <style jsx global>{`
        .kua-marker-wrapper { background: transparent !important; border: none !important; }
        .kua-marker { position: relative; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; color: var(--kua-color); }
        .kua-marker__ring { position: absolute; inset: 0; border-radius: 9999px; border: 1px solid var(--kua-color); box-shadow: 0 0 12px color-mix(in srgb, var(--kua-color) 60%, transparent), inset 0 0 12px color-mix(in srgb, var(--kua-color) 40%, transparent); animation: kua-ping 2.4s ease-out infinite; opacity: 0.65; }
        .kua-marker__core { position: relative; width: 26px; height: 26px; border-radius: 9999px; display: flex; align-items: center; justify-content: center; font-family: var(--font-mono); font-size: 10px; font-weight: 600; color: #05070a; background: var(--kua-color); box-shadow: 0 0 14px color-mix(in srgb, var(--kua-color) 70%, transparent); }
        @keyframes kua-ping { 0% { transform: scale(0.9); opacity: 0.85; } 70% { transform: scale(1.6); opacity: 0; } 100% { transform: scale(1.6); opacity: 0; } }
      `}</style>

      <MapContainer
        center={BARCELONA_CENTER}
        zoom={12}
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
          {valid.map((m) => {
            const tier = laundryTier(m.score ?? null);
            const meta = laundryStatusMeta(m.deal_status);
            const color = m.deal_status === "approved_candidate" ? meta.color : tier.color;
            return (
              <Marker
                key={m.id}
                position={[m.lat, m.lng]}
                icon={buildIcon(m.score, color)}
              >
                <Popup>
                  <div className="min-w-[220px] space-y-2 font-mono">
                    <div className="font-display text-xs font-semibold text-foreground">
                      {m.address || "Laundromat"}
                    </div>
                    <div className="text-[10px] text-muted-foreground">
                      {m.city || "—"}
                    </div>
                    <div className="text-[11px]">
                      <strong>Score:</strong> {m.score ?? "—"} · {m.verdict || "—"}
                    </div>
                    <Link
                      href={`/laundry/property/${m.id}`}
                      className="block rounded-md border border-violet-400/40 bg-violet-400/10 px-2.5 py-1.5 text-center text-[10px] uppercase tracking-widest text-violet-300 hover:bg-violet-400/20"
                    >
                      Open memo
                    </Link>
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MarkerClusterGroup>
      </MapContainer>

      <div className="pointer-events-none absolute left-3 top-3 z-[400] flex flex-col gap-1">
        <div className="rounded-md border border-border/60 bg-card/80 px-3 py-2 backdrop-blur-xl">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Laundry sector
          </div>
          <div className="font-display text-sm font-semibold text-foreground">
            {valid.length} plotted
            {totalCount != null ? ` / ${totalCount} scanned` : ""}
          </div>
        </div>
        {missingCount > 0 && (
          <div className="rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-2 backdrop-blur-xl">
            <div className="font-mono text-[10px] uppercase tracking-widest text-amber-200">
              Missing coordinates
            </div>
            <div className="text-[11px] text-muted-foreground">{missingCount} not shown on map</div>
          </div>
        )}
      </div>
    </div>
  );
}
