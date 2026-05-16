import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx,mdx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1600px" },
    },
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular"],
        display: ["var(--font-display)", "var(--font-sans)"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        kua: {
          ink: "#05070A",
          panel: "#0A0D12",
          surface: "#0E1218",
          line: "#1A2030",
          text: "#E7ECF4",
          mute: "#7C8699",
          cyan: "#38E1FF",
          neon: "#7CFAB3",
          amber: "#F5B400",
          rose: "#FF4D6D",
          violet: "#9C7BFF",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      backgroundImage: {
        "grid-lines":
          "linear-gradient(to right, rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.04) 1px, transparent 1px)",
        "radial-glow":
          "radial-gradient(circle at 50% 0%, rgba(56,225,255,0.10), transparent 60%)",
        "scanline":
          "linear-gradient(to bottom, transparent 0%, rgba(56,225,255,0.08) 50%, transparent 100%)",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(56,225,255,0.25), 0 0 24px rgba(56,225,255,0.18)",
        "glow-neon": "0 0 0 1px rgba(124,250,179,0.25), 0 0 24px rgba(124,250,179,0.18)",
        "glow-rose": "0 0 0 1px rgba(255,77,109,0.25), 0 0 24px rgba(255,77,109,0.18)",
        panel:
          "inset 0 1px 0 rgba(255,255,255,0.04), 0 12px 40px -16px rgba(0,0,0,0.7)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-glow": {
          "0%,100%": { opacity: "0.6", filter: "drop-shadow(0 0 6px rgba(56,225,255,0.35))" },
          "50%": { opacity: "1", filter: "drop-shadow(0 0 14px rgba(56,225,255,0.7))" },
        },
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
        marquee: {
          "0%": { transform: "translateX(0%)" },
          "100%": { transform: "translateX(-50%)" },
        },
        "radar-sweep": {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
        ticker: {
          "0%": { opacity: "0.3" },
          "50%": { opacity: "1" },
          "100%": { opacity: "0.3" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-up": "fade-up 0.45s cubic-bezier(0.16,1,0.3,1) both",
        "pulse-glow": "pulse-glow 2.4s ease-in-out infinite",
        scan: "scan 3.2s linear infinite",
        marquee: "marquee 40s linear infinite",
        "radar-sweep": "radar-sweep 4s linear infinite",
        ticker: "ticker 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
