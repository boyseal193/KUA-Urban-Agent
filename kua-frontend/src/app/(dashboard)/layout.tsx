import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth/session";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { StatusTicker } from "@/components/layout/status-ticker";
import { AuthGuard } from "@/components/auth/auth-guard";

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
              {children}
            </div>
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
