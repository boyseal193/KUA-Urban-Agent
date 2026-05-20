import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth/session";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { StatusTicker } from "@/components/layout/status-ticker";
import { AuthGuard } from "@/components/auth/auth-guard";
import { ErrorBoundary } from "@/components/error-boundary";

/**
 * Server-rendered dashboard shell.
 *
 * Auth enforcement order:
 *   1. middleware.ts checks the cookie + JWT on every request (Edge runtime)
 *   2. THIS layout double-checks server-side via getSession()
 *   3. <AuthGuard> is a passive client-side render guard
 *   4. <ErrorBoundary> catches any client render errors so a single bad
 *      component never white-screens the whole dashboard.
 */
export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getSession();
  if (!session) redirect("/login");

  return (
    <AuthGuard>
      <div className="relative z-10 flex min-h-screen">
        <Sidebar />
        <div className="flex min-h-screen w-full min-w-0 flex-col">
          <Topbar />
          <StatusTicker />
          <main className="relative flex-1 overflow-x-hidden">
            <div className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
              <ErrorBoundary>{children}</ErrorBoundary>
            </div>
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
