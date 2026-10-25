import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogClose,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Plus, Trash2, FolderOpen, Users, Database, Activity, Presentation } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const statusColors = {
  created: "bg-[#6E7681]/20 text-[#8B949E] border-[#6E7681]/30",
  data_uploaded: "bg-[#F59E0B]/15 text-[#F59E0B] border-[#F59E0B]/30",
  analyzed: "bg-[#10B981]/15 text-[#10B981] border-[#10B981]/30",
};

export default function Dashboard() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newCase, setNewCase] = useState({ name: "", description: "" });
  const [dialogOpen, setDialogOpen] = useState(false);
  const navigate = useNavigate();

  const fetchCases = async () => {
    try {
      const res = await axios.get(`${API}/cases`);
      setCases(res.data);
    } catch (e) {
      toast.error("Failed to load cases");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCases(); }, []);

  const createCase = async () => {
    if (!newCase.name.trim()) { toast.error("Case name is required"); return; }
    try {
      await axios.post(`${API}/cases`, newCase);
      toast.success("Case created");
      setNewCase({ name: "", description: "" });
      setDialogOpen(false);
      fetchCases();
    } catch (e) {
      toast.error("Failed to create case");
    }
  };

  const deleteCase = async (id) => {
    try {
      await axios.delete(`${API}/cases/${id}`);
      toast.success("Case deleted");
      fetchCases();
    } catch (e) {
      toast.error("Failed to delete case");
    }
  };

  const downloadBriefingDeck = async () => {
    try {
      toast.info("Generating briefing deck...");
      const res = await axios.get(`${API}/briefing-deck`, { responseType: "blob" });
      const blob = new Blob([res.data], {
        type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
      a.download = `AMBER_Briefing_${today}.pptx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Briefing deck downloaded");
    } catch (e) {
      toast.error("Failed to generate briefing deck");
    }
  };

  const totalRecords = cases.reduce((sum, c) => sum + (c.record_count || 0), 0);
  const analyzedCases = cases.filter((c) => c.status === "analyzed").length;

  return (
    <div data-testid="dashboard-page" className="p-6 animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 data-testid="dashboard-title" className="text-3xl font-bold text-[#E1E7EF] font-chivo tracking-tight">
            Intelligence Dashboard
          </h1>
          <p className="text-sm text-[#6E7681] mt-1">CDR & IPDR Analysis Control Center</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <div className="flex items-center gap-2">
            <Button
              data-testid="briefing-deck-btn"
              onClick={downloadBriefingDeck}
              variant="outline"
              className="border-[#C8A951] text-[#C8A951] hover:bg-[#C8A951]/10 rounded-sm text-sm"
              title="Download senior-officer briefing deck (.pptx)"
            >
              <Presentation className="w-4 h-4 mr-1" /> Briefing Deck
            </Button>
            <DialogTrigger asChild>
              <Button data-testid="create-case-btn" className="bg-[#0047FF] hover:bg-[#003BD6] text-white rounded-sm text-sm">
                <Plus className="w-4 h-4 mr-1" /> New Case
              </Button>
            </DialogTrigger>
          </div>
          <DialogContent className="bg-[#13151A] border-[#2D333B]">
            <DialogHeader>
              <DialogTitle className="text-[#E1E7EF] font-chivo">Create New Case</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 py-2">
              <div>
                <Label className="text-[#8B949E] text-xs uppercase tracking-[0.15em]">Case Name</Label>
                <Input
                  data-testid="case-name-input"
                  value={newCase.name}
                  onChange={(e) => setNewCase({ ...newCase, name: e.target.value })}
                  className="bg-[#090A0C] border-[#2D333B] text-[#E1E7EF] rounded-sm mt-1"
                  placeholder="e.g., Operation Nightfall"
                />
              </div>
              <div>
                <Label className="text-[#8B949E] text-xs uppercase tracking-[0.15em]">Description</Label>
                <Input
                  data-testid="case-desc-input"
                  value={newCase.description}
                  onChange={(e) => setNewCase({ ...newCase, description: e.target.value })}
                  className="bg-[#090A0C] border-[#2D333B] text-[#E1E7EF] rounded-sm mt-1"
                  placeholder="Brief description..."
                />
              </div>
            </div>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" className="border-[#2D333B] text-[#8B949E] rounded-sm">Cancel</Button>
              </DialogClose>
              <Button data-testid="confirm-create-btn" onClick={createCase} className="bg-[#0047FF] hover:bg-[#003BD6] text-white rounded-sm">
                Create Case
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        {[
          { label: "Total Cases", value: cases.length, icon: FolderOpen, color: "#0047FF" },
          { label: "Analyzed", value: analyzedCases, icon: Activity, color: "#10B981" },
          { label: "Total Records", value: totalRecords.toLocaleString(), icon: Database, color: "#F59E0B" },
          { label: "Subjects", value: cases.reduce((s, c) => s + (c.subjects?.length || 0), 0), icon: Users, color: "#A78BFA" },
        ].map((stat) => (
          <Card key={stat.label} className="bg-[#13151A] border-[#2D333B] rounded-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 rounded-sm" style={{ background: `${stat.color}15` }}>
                <stat.icon className="w-4 h-4" style={{ color: stat.color }} />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.15em] text-[#6E7681]">{stat.label}</p>
                <p className="text-xl font-bold text-[#E1E7EF] font-mono">{stat.value}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Case List */}
      {loading ? (
        <div className="text-center py-12 text-[#6E7681]">Loading cases...</div>
      ) : cases.length === 0 ? (
        <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
          <CardContent className="p-12 text-center">
            <FolderOpen className="w-10 h-10 text-[#2D333B] mx-auto mb-3" />
            <p className="text-[#8B949E] text-sm">No cases yet. Create your first case to start analyzing.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {cases.map((c, idx) => (
            <Card
              key={c.id}
              data-testid={`case-card-${idx}`}
              className="bg-[#13151A] border-[#2D333B] rounded-sm hover:border-[#0047FF]/40 transition-colors cursor-pointer group"
              onClick={() => navigate(`/cases/${c.id}`)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <CardTitle className="text-base font-chivo text-[#E1E7EF] group-hover:text-[#0047FF] transition-colors">
                    {c.name}
                  </CardTitle>
                  <Badge className={`rounded-sm text-[10px] ${statusColors[c.status] || statusColors.created}`}>
                    {c.status?.replace("_", " ").toUpperCase()}
                  </Badge>
                </div>
                {c.description && <p className="text-xs text-[#6E7681] mt-1">{c.description}</p>}
              </CardHeader>
              <CardContent className="pt-0">
                <div className="flex items-center gap-4 text-xs text-[#8B949E]">
                  <span className="font-mono">{c.subjects?.length || 0} subjects</span>
                  <span className="font-mono">{c.upload_count || 0} files</span>
                  <span className="font-mono">{(c.record_count || 0).toLocaleString()} records</span>
                </div>
                <div className="flex items-center justify-between mt-3">
                  <span className="text-[10px] text-[#6E7681]">
                    {new Date(c.created_at).toLocaleDateString()}
                  </span>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button
                        data-testid={`delete-case-${idx}`}
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-[#6E7681] hover:text-[#E63946] hover:bg-[#E63946]/10"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent className="bg-[#13151A] border-[#2D333B]" onClick={(e) => e.stopPropagation()}>
                      <AlertDialogHeader>
                        <AlertDialogTitle className="text-[#E1E7EF]">Delete Case</AlertDialogTitle>
                        <AlertDialogDescription className="text-[#8B949E]">
                          This will permanently delete "{c.name}" and all associated data.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel className="border-[#2D333B] text-[#8B949E] rounded-sm">Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          data-testid={`confirm-delete-${idx}`}
                          className="bg-[#E63946] hover:bg-[#D92D39] text-white rounded-sm"
                          onClick={(e) => { e.stopPropagation(); deleteCase(c.id); }}
                        >
                          Delete
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
