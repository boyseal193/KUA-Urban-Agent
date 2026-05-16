"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion } from "framer-motion";
import { FileText, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useRegenerateMemo } from "@/hooks/use-deals";
import { toast } from "sonner";

interface ICMemoViewerProps {
  memo: string | null | undefined;
  propertyId: string;
  className?: string;
}

export function ICMemoViewer({ memo, propertyId, className }: ICMemoViewerProps) {
  const regenerate = useRegenerateMemo();

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className={`panel relative overflow-hidden ${className ?? ""}`}
    >
      <div className="flex items-center justify-between border-b border-border/60 px-5 py-3">
        <div className="flex items-center gap-2">
          <FileText className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            Investment Committee Memo
          </h3>
        </div>
        <Button
          size="sm"
          variant="tactical"
          disabled={regenerate.isPending}
          onClick={() =>
            regenerate
              .mutateAsync(propertyId)
              .then(() => toast.success("IC memo regenerated"))
              .catch((e) =>
                toast.error("Regeneration failed", {
                  description: e?.message ?? "Unknown error",
                })
              )
          }
        >
          {regenerate.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" />
          )}
          Regenerate
        </Button>
      </div>

      <ScrollArea className="max-h-[680px]">
        <article className="markdown-memo px-6 py-5">
          {memo ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{memo}</ReactMarkdown>
          ) : (
            <div className="py-10 text-center text-sm text-muted-foreground">
              No memo on file. Trigger regeneration to draft one.
            </div>
          )}
        </article>
      </ScrollArea>
    </motion.div>
  );
}
