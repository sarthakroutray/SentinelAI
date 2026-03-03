import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen bg-zinc-950">
      <Sidebar />
      <div className="flex flex-1 flex-col pl-56">
        <Header />
        <main className="flex-1 px-6 py-7">{children}</main>
      </div>
    </div>
  );
}
