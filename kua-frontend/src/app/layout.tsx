import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";

import { AppProviders } from "@/providers";
import { GridOverlay, RadialGlow } from "@/components/common/grid-overlay";
import { getSession } from "@/lib/auth/session";
import { APP_NAME, APP_SHORT } from "@/lib/constants";

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});
const display = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: `${APP_NAME} · ${APP_SHORT}`,
    template: `%s · ${APP_SHORT}`,
  },
  description:
    "K.U.A. — AI-powered urban acquisitions intelligence for Barcelona commercial real estate and self-storage conversions.",
  applicationName: APP_NAME,
  keywords: [
    "real estate",
    "acquisitions",
    "AI underwriting",
    "self-storage",
    "Barcelona",
    "institutional",
  ],
  authors: [{ name: "KLAVE" }],
  openGraph: {
    title: APP_NAME,
    description:
      "AI urban acquisition intelligence platform — Barcelona commercial real estate.",
    type: "website",
  },
  icons: { icon: "/favicon.ico" },
};

export const viewport: Viewport = {
  themeColor: "#05070A",
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getSession();
  return (
    <html
      lang="en"
      className={`${sans.variable} ${mono.variable} ${display.variable} dark`}
      suppressHydrationWarning
    >
      <body className="min-h-screen bg-background text-foreground antialiased">
        <RadialGlow />
        <GridOverlay />
        <AppProviders initialUser={user}>{children}</AppProviders>
      </body>
    </html>
  );
}
