import "@/App.css";
import { BrowserRouter, Routes, Route, Link, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { Shield, LayoutDashboard, FileText, GitCompare } from "lucide-react";
import Dashboard from "@/pages/Dashboard";
import CaseView from "@/pages/CaseView";
import Compare from "@/pages/Compare";

function Sidebar() {
  const location = useLocation();
  const isHome = location.pathname === "/";
  const isCompare = location.pathname === "/compare";

  return (
    <aside data-testid="sidebar" className="w-56 bg-[#13151A] border-r border-[#2D333B] h-screen fixed left-0 top-0 flex flex-col z-40">
      <div className="p-4 border-b border-[#2D333B]">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-[#0047FF]" />
          <h1 className="text-base font-bold text-[#E1E7EF] font-chivo tracking-tight">SIGINT</h1>
        </div>
        <p className="text-[10px] uppercase tracking-[0.2em] text-[#6E7681] mt-1">CDR / IPDR Analysis</p>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        <Link
          to="/"
          data-testid="nav-dashboard"
          className={`flex items-center gap-2 px-3 py-2 rounded-sm text-sm transition-colors ${
            isHome ? "bg-[#0047FF] text-white" : "text-[#8B949E] hover:bg-[#1C1F26] hover:text-[#E1E7EF]"
          }`}
        >
          <LayoutDashboard className="w-4 h-4" />
          Dashboard
        </Link>
        <Link
          to="/compare"
          data-testid="nav-compare"
          className={`flex items-center gap-2 px-3 py-2 rounded-sm text-sm transition-colors ${
            isCompare ? "bg-[#0047FF] text-white" : "text-[#8B949E] hover:bg-[#1C1F26] hover:text-[#E1E7EF]"
          }`}
        >
          <GitCompare className="w-4 h-4" />
          Compare Cases
        </Link>
        {!isHome && !isCompare && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-sm text-sm text-[#0047FF] bg-[#0047FF]/10">
            <FileText className="w-4 h-4" />
            Case Detail
          </div>
        )}
      </nav>
      <div className="p-3 border-t border-[#2D333B]">
        <p className="text-[10px] text-[#6E7681]">Intelligence Analysis Tool</p>
        <p className="text-[10px] text-[#6E7681]">Rule-Based Engine v1.0</p>
      </div>
    </aside>
  );
}

function AppLayout() {
  return (
    <div className="flex min-h-screen bg-[#090A0C]">
      <Sidebar />
      <main className="flex-1 ml-56">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/cases/:caseId" element={<CaseView />} />
          <Route path="/compare" element={<Compare />} />
        </Routes>
      </main>
      <Toaster position="top-right" theme="dark" />
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  );
}

export default App;
