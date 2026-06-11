/** Frontend Google Maps JavaScript API configuration. */

export const GOOGLE_MAPS_API_KEY =
  process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY?.trim() || "";

export const GOOGLE_MAPS_CONFIGURED = Boolean(GOOGLE_MAPS_API_KEY);

/** Load the Maps JS API once (for optional Google basemap / Places). */
export function loadGoogleMapsScript(): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(false);
  if (!GOOGLE_MAPS_CONFIGURED) return Promise.resolve(false);
  if ((window as unknown as { google?: { maps?: unknown } }).google?.maps) {
    return Promise.resolve(true);
  }

  return new Promise((resolve) => {
    const existing = document.getElementById("google-maps-js");
    if (existing) {
      existing.addEventListener("load", () => resolve(true), { once: true });
      existing.addEventListener("error", () => resolve(false), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.id = "google-maps-js";
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(
      GOOGLE_MAPS_API_KEY,
    )}&libraries=places`;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.head.appendChild(script);
  });
}
