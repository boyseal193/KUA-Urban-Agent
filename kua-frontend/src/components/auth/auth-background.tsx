"use client";

import { motion } from "framer-motion";

/**
 * Cinematic animated background for the login screen.
 * Pure CSS + Framer Motion — no canvas, no perf hit.
 */
export function AuthBackground() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {/* Grid */}
      <div className="absolute inset-0 grid-bg opacity-40 mask-fade-b" />

      {/* Soft radial glows */}
      <div
        className="absolute -top-1/3 left-1/4 h-[800px] w-[800px] rounded-full opacity-50"
        style={{
          background:
            "radial-gradient(circle, rgba(56,225,255,0.18), transparent 60%)",
        }}
      />
      <div
        className="absolute -bottom-1/3 right-1/4 h-[700px] w-[700px] rounded-full opacity-40"
        style={{
          background:
            "radial-gradient(circle, rgba(124,250,179,0.14), transparent 60%)",
        }}
      />

      {/* Sweeping scanline */}
      <motion.div
        className="absolute inset-x-0 h-[42%] mix-blend-screen"
        style={{
          background:
            "linear-gradient(to bottom, transparent, rgba(56,225,255,0.08) 50%, transparent)",
        }}
        animate={{ y: ["-60%", "120%"] }}
        transition={{ duration: 7, repeat: Infinity, ease: "linear" }}
      />

      {/* Concentric radar rings */}
      <div className="absolute -bottom-32 -right-32 h-[600px] w-[600px] opacity-25">
        {[1, 2, 3, 4].map((i) => (
          <motion.span
            key={i}
            className="absolute inset-0 m-auto rounded-full border border-primary/30"
            style={{ width: `${i * 120}px`, height: `${i * 120}px` }}
            animate={{ opacity: [0.2, 0.6, 0.2] }}
            transition={{
              duration: 3,
              delay: i * 0.4,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />
        ))}
        <motion.div
          className="absolute inset-0 origin-center"
          style={{
            background:
              "conic-gradient(from 0deg, transparent 0deg, rgba(56,225,255,0.35) 30deg, transparent 60deg)",
          }}
          animate={{ rotate: 360 }}
          transition={{ duration: 5, repeat: Infinity, ease: "linear" }}
        />
      </div>

      {/* Vignette */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 30%, rgba(5,7,10,0.7) 100%)",
        }}
      />
    </div>
  );
}
