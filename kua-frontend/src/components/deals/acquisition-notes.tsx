"use client";

import * as React from "react";
import { PencilLine, Plus, Save } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Note {
  id: string;
  body: string;
  at: number;
}

/**
 * Local-only acquisition notebook.
 * Persists to localStorage per-property until a `/notes` endpoint is added.
 */
export function AcquisitionNotes({
  propertyId,
  className,
}: {
  propertyId: string;
  className?: string;
}) {
  const storageKey = `kua:notes:${propertyId}`;
  const [notes, setNotes] = React.useState<Note[]>([]);
  const [draft, setDraft] = React.useState("");

  React.useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) setNotes(JSON.parse(raw));
    } catch {}
  }, [storageKey]);

  function persist(next: Note[]) {
    setNotes(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {}
  }

  function add() {
    const body = draft.trim();
    if (!body) return;
    const note: Note = {
      id: crypto.randomUUID(),
      body,
      at: Date.now(),
    };
    persist([note, ...notes]);
    setDraft("");
  }

  return (
    <div className={`panel p-5 ${className ?? ""}`}>
      <header className="mb-3 flex items-center justify-between border-b border-border/60 pb-3">
        <div className="flex items-center gap-2">
          <PencilLine className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            Acquisition Notes
          </h3>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {notes.length} entries · local
        </span>
      </header>

      <div className="space-y-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Capture context, broker conversations, technical concerns…"
          rows={3}
          className="w-full resize-none rounded-md border border-border/60 bg-background/40 px-3 py-2 text-sm placeholder:text-muted-foreground/60 focus:border-primary/40 focus:outline-none focus:ring-2 focus:ring-primary/40"
        />
        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            size="sm"
            variant="tactical"
            onClick={add}
            disabled={!draft.trim()}
            className="gap-1.5"
          >
            <Plus className="h-3 w-3" /> Add note
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => persist(notes)}
            className="gap-1.5"
          >
            <Save className="h-3 w-3" /> Save
          </Button>
        </div>
      </div>

      <ul className="mt-4 space-y-2">
        {notes.length === 0 && (
          <li className="rounded-md border border-dashed border-border/60 bg-white/[0.01] p-4 text-center text-xs text-muted-foreground">
            No acquisition notes yet for this property.
          </li>
        )}
        {notes.map((n) => (
          <li
            key={n.id}
            className="rounded-md border border-border/40 bg-white/[0.02] p-3"
          >
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
              {n.body}
            </p>
            <div className="mt-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {new Date(n.at).toLocaleString("en-EU")}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
