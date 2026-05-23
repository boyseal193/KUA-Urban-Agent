"use client";

/**
 * Stale-property registry.
 *
 * After a property is soft-deleted (or detected as deleted by the backend),
 * its id is added to this registry so EVERY list, feed and detail page can
 * synchronously hide it — even before React-Query has had a chance to
 * refetch the source-of-truth.
 *
 * The registry is persisted to ``localStorage`` so a refresh doesn't
 * resurrect ghost cards from a fresh cache miss, and is shared across tabs
 * via the ``storage`` event.
 */

import * as React from "react";

const STORAGE_KEY = "kua:stale-property-ids:v1";
const MAX_ENTRIES = 500; // hard cap so the set can't grow unbounded

type Listener = (ids: ReadonlySet<string>) => void;

class StalePropertyRegistry {
  private ids = new Set<string>();
  private listeners = new Set<Listener>();
  private hydrated = false;

  private hydrate() {
    if (this.hydrated || typeof window === "undefined") return;
    this.hydrated = true;
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed: unknown = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          for (const v of parsed) {
            if (typeof v === "string" && v) this.ids.add(v);
          }
        }
      }
    } catch {
      /* ignore corrupted storage */
    }

    window.addEventListener("storage", (e) => {
      if (e.key !== STORAGE_KEY) return;
      this.ids = new Set();
      try {
        const parsed: unknown = e.newValue ? JSON.parse(e.newValue) : [];
        if (Array.isArray(parsed)) {
          for (const v of parsed) {
            if (typeof v === "string" && v) this.ids.add(v);
          }
        }
      } catch {
        /* ignore */
      }
      this.notify();
    });
  }

  private persist() {
    if (typeof window === "undefined") return;
    try {
      // Trim oldest entries (Set preserves insertion order).
      while (this.ids.size > MAX_ENTRIES) {
        const first = this.ids.values().next().value;
        if (first === undefined) break;
        this.ids.delete(first);
      }
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(this.ids)));
    } catch {
      /* ignore quota errors */
    }
  }

  private notify() {
    const snapshot: ReadonlySet<string> = new Set(this.ids);
    for (const l of this.listeners) {
      try {
        l(snapshot);
      } catch {
        /* listener errors must not break the registry */
      }
    }
  }

  add(id: string | null | undefined) {
    this.hydrate();
    if (!id) return;
    if (this.ids.has(id)) return;
    this.ids.add(id);
    this.persist();
    this.notify();
  }

  addMany(ids: Iterable<string>) {
    this.hydrate();
    let changed = false;
    for (const id of ids) {
      if (id && !this.ids.has(id)) {
        this.ids.add(id);
        changed = true;
      }
    }
    if (changed) {
      this.persist();
      this.notify();
    }
  }

  remove(id: string) {
    this.hydrate();
    if (this.ids.delete(id)) {
      this.persist();
      this.notify();
    }
  }

  has(id: string | null | undefined): boolean {
    this.hydrate();
    if (!id) return false;
    return this.ids.has(id);
  }

  snapshot(): ReadonlySet<string> {
    this.hydrate();
    return new Set(this.ids);
  }

  subscribe(listener: Listener): () => void {
    this.hydrate();
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

export const staleProperties = new StalePropertyRegistry();

/**
 * React hook returning a stable predicate ``isStale(id)``.
 * Components re-render automatically when the registry changes.
 */
export function useStaleProperties() {
  const [version, setVersion] = React.useState(0);

  React.useEffect(() => {
    return staleProperties.subscribe(() => setVersion((v) => v + 1));
  }, []);

  const isStale = React.useCallback(
    (id: string | null | undefined) => staleProperties.has(id),
    // version is in deps so consumers re-evaluate after registry mutations
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [version]
  );

  const filter = React.useCallback(
    <T extends { property_id?: string | null; id?: string | null }>(rows: T[] | null | undefined) => {
      if (!Array.isArray(rows)) return [] as T[];
      return rows.filter((r) => !isStale(r?.property_id ?? r?.id ?? null));
    },
    [isStale]
  );

  return { isStale, filter };
}
