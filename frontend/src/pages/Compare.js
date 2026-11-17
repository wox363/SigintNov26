import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  GitCompare, Phone, Smartphone, CreditCard, Globe, UserCheck,
  FileText, Download, AlertCircle, Loader2, ChevronRight, FileDown,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const strengthColor = (s) => ({
  EXACT: "#E63946", STRONG: "#F59E0B", POSSIBLE: "#FBBF24",
}[s] || "#8B949E");

export default function Compare() {
  const [cases, setCases] = useState([]);
  const [selected, setSelected] = useState({});
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${API}/cases?limit=1000`);
        const all = Array.isArray(res.data) ? res.data : (res.data.cases || []);
        setCases(all.filter((c) => c.status === "analyzed"));
      } catch (e) {
        toast.error("Failed to load cases");
      }
    })();
  }, []);

  const selectedIds = Object.keys(selected).filter((k) => selected[k]);

  const toggle = (id) => setSelected((s) => ({ ...s, [id]: !s[id] }));

  const runCompare = async () => {
    if (selectedIds.length < 2) {
      toast.error("Select at least 2 cases to compare");
      return;
    }
    setLoading(true);
    try {
      const res = await axios.post(`${API}/compare`, { case_ids: selectedIds });
      setComparison(res.data);
      toast.success(`Comparison complete — ${res.data.summary.case_count} cases analyzed`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Comparison failed");
    } finally {
      setLoading(false);
    }
  };

  const downloadReport = async (fmt) => {
    if (!comparison?.id) return;
    setDownloading(fmt);
    try {
      const res = await axios.get(`${API}/compare/${comparison.id}/report/${fmt}`, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `Cross_Case_Comparison.${fmt}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(`Failed to download ${fmt.toUpperCase()}`);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div data-testid="compare-page" className="min-h-screen bg-[#090A0C]">
      {/* Header */}
      <div className="border-b border-[#2D333B] bg-[#0D0F14] sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center gap-3">
            <GitCompare className="w-5 h-5 text-[#0047FF]" />
            <div>
              <h1 className="text-base font-bold text-[#E1E7EF] font-chivo tracking-tight">
                Cross-Case Comparison
              </h1>
              <p className="text-[10px] uppercase tracking-[0.2em] text-[#6E7681] mt-0.5">
                Find recurring suspects, devices &amp; channels across investigations
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-4">
        {/* Case picker */}
        <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-chivo text-[#E1E7EF] flex items-center gap-2">
              <FileText className="w-4 h-4 text-[#0047FF]" />
              <span className="flex-1">Step 1 — Select cases to compare</span>
              <Badge className="rounded-sm text-[10px] bg-[#0047FF]/20 text-[#0047FF] border-[#0047FF]/40">
                {selectedIds.length} selected
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {cases.length === 0 ? (
              <p className="text-xs text-[#6E7681] text-center py-4">
                No analyzed cases available. Run analysis on at least 2 cases first.
              </p>
            ) : (
              <ScrollArea className="max-h-72">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pr-2">
                  {cases.map((c) => {
                    const isSel = !!selected[c.id];
                    return (
                      <div
                        key={c.id}
                        role="button"
                        tabIndex={0}
                        data-testid={`case-select-${c.id}`}
                        onClick={() => toggle(c.id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggle(c.id);
                          }
                        }}
                        className={`flex items-start gap-3 p-2 rounded-sm border text-left transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[#0047FF] ${
                          isSel
                            ? "border-[#0047FF] bg-[#0047FF]/10"
                            : "border-[#2D333B] bg-[#0D0F14] hover:bg-[#13151A]"
                        }`}
                      >
                        <Checkbox checked={isSel} className="mt-0.5 pointer-events-none" />
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium text-[#E1E7EF] truncate">{c.name}</div>
                          <div className="text-[10px] text-[#6E7681] mt-0.5 flex items-center gap-2 font-mono">
                            <span>{c.subjects?.length || 0} subjects</span>
                            <span className="text-[#2D333B]">·</span>
                            <span>{c.record_count?.toLocaleString() || 0} records</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </ScrollArea>
            )}
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-[#2D333B]">
              <span className="text-[10px] text-[#6E7681]">
                {selectedIds.length < 2
                  ? "Select 2 or more cases"
                  : `${selectedIds.length} cases ready to compare`}
              </span>
              <Button
                data-testid="run-compare-btn"
                onClick={runCompare}
                disabled={selectedIds.length < 2 || loading}
                size="sm"
                className="bg-[#0047FF] hover:bg-[#003BD6] text-white rounded-sm text-xs"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-3 h-3 mr-1.5 animate-spin" />
                    Comparing...
                  </>
                ) : (
                  <>
                    <GitCompare className="w-3 h-3 mr-1.5" />
                    Run Comparison
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        {comparison && <ComparisonResults comparison={comparison} onDownload={downloadReport} downloading={downloading} />}
      </div>
    </div>
  );
}

function ComparisonResults({ comparison, onDownload, downloading }) {
  const s = comparison.summary || {};
  return (
    <>
      {/* Exec summary */}
      <Card data-testid="compare-summary" className="bg-[#13151A] border-[#0047FF]/30 rounded-sm">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <UserCheck className="w-4 h-4 text-[#0047FF]" />
            <span className="text-xs font-chivo font-bold text-[#E1E7EF] uppercase tracking-[0.15em]">
              Comparison Summary
            </span>
            <div className="ml-auto flex gap-1.5">
              <Button
                data-testid="download-compare-pdf"
                onClick={() => onDownload("pdf")}
                disabled={!!downloading}
                size="sm"
                className="h-7 text-[10px] rounded-sm bg-[#E63946]/20 text-[#E63946] hover:bg-[#E63946]/30 border border-[#E63946]/40"
              >
                {downloading === "pdf" ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <FileDown className="w-3 h-3 mr-1" />}
                PDF
              </Button>
              <Button
                data-testid="download-compare-docx"
                onClick={() => onDownload("docx")}
                disabled={!!downloading}
                size="sm"
                className="h-7 text-[10px] rounded-sm bg-[#0047FF]/20 text-[#0047FF] hover:bg-[#0047FF]/30 border border-[#0047FF]/40"
              >
                {downloading === "docx" ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Download className="w-3 h-3 mr-1" />}
                Word
              </Button>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3">
            <StatBox label="Cases" value={s.case_count} color="#0047FF" />
            <StatBox label="Phones" value={s.shared_phones_count} color="#10B981" icon={Phone} />
            <StatBox label="IMEIs" value={s.shared_imeis_count} color="#F59E0B" icon={Smartphone} />
            <StatBox label="IMSIs" value={s.shared_imsis_count} color="#06B6D4" icon={CreditCard} />
            <StatBox label="IPs" value={s.shared_ips_count} color="#A78BFA" icon={Globe} />
          </div>
          {s.aliases_count > 0 && (
            <div className="mb-3">
              <Badge className="rounded-sm bg-[#E63946]/20 text-[#E63946] border-[#E63946]/40 text-[10px]">
                {s.aliases_count} alias match(es)
              </Badge>
            </div>
          )}
          <div className="space-y-1 pt-3 border-t border-[#2D333B]">
            {(s.key_findings || []).map((f, i) => (
              <p key={i} className="text-[11px] text-[#8B949E] flex items-start gap-1.5">
                <ChevronRight className="w-3 h-3 mt-0.5 text-[#0047FF] flex-shrink-0" />
                <span>{f}</span>
              </p>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Cases compared */}
      <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-chivo text-[#E1E7EF]">Cases Included</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-1">
            {(comparison.case_metadata || []).map((m, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 p-2 bg-[#0D0F14] rounded-sm border border-[#2D333B]" data-testid={`compare-case-${m.case_id}`}>
                <span className="text-xs text-[#E1E7EF] font-medium">{m.case_name}</span>
                <span className="text-[10px] text-[#6E7681]">·</span>
                <span className="text-[10px] text-[#8B949E]">
                  {m.subject_count} subjects: <span className="text-[#E1E7EF] font-mono">{m.subjects.join(", ") || "—"}</span>
                </span>
                {m.high_risk_subjects?.length > 0 && (
                  <Badge className="rounded-sm text-[9px] bg-[#E63946]/20 text-[#E63946] border-[#E63946]/40">
                    {m.high_risk_subjects.length} HIGH-RISK
                  </Badge>
                )}
                <span className="ml-auto text-[10px] text-[#6E7681] font-mono">
                  P:{m.total_phones} · I:{m.total_imeis} · S:{m.total_imsis} · IP:{m.total_ips}
                </span>
              </div>
            ))}
            {(comparison.missing || []).map((m, i) => (
              <div key={i} className="flex items-center gap-2 p-2 bg-[#E63946]/5 rounded-sm border border-[#E63946]/20">
                <AlertCircle className="w-3 h-3 text-[#E63946]" />
                <span className="text-[10px] text-[#E63946]">
                  Excluded: {m.case_name || m.case_id} — {m.reason}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Tabbed sections */}
      <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
        <CardContent className="p-4">
          <Tabs defaultValue="phones">
            <TabsList className="bg-[#0D0F14] border border-[#2D333B] rounded-sm h-auto p-1 mb-3">
              <TabTrigger v="phones" label="Phones" count={s.shared_phones_count} icon={Phone} />
              <TabTrigger v="imeis" label="IMEIs" count={s.shared_imeis_count} icon={Smartphone} />
              <TabTrigger v="imsis" label="IMSIs" count={s.shared_imsis_count} icon={CreditCard} />
              <TabTrigger v="ips" label="IPs" count={s.shared_ips_count} icon={Globe} />
              <TabTrigger v="aliases" label="Aliases" count={s.aliases_count} icon={UserCheck} />
            </TabsList>
            <TabsContent value="phones">
              <SharedEntityList items={comparison.shared_phones} label="phone number" />
            </TabsContent>
            <TabsContent value="imeis">
              <SharedEntityList items={comparison.shared_imeis} label="IMEI" />
            </TabsContent>
            <TabsContent value="imsis">
              <SharedEntityList items={comparison.shared_imsis} label="IMSI" />
            </TabsContent>
            <TabsContent value="ips">
              <SharedEntityList items={comparison.shared_ips} label="destination IP" />
            </TabsContent>
            <TabsContent value="aliases">
              <AliasList items={comparison.aliases} />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </>
  );
}

function TabTrigger({ v, label, count, icon: Icon }) {
  return (
    <TabsTrigger
      value={v}
      data-testid={`compare-tab-${v}`}
      className="rounded-sm text-xs h-8 data-[state=active]:bg-[#0047FF] data-[state=active]:text-white text-[#8B949E]"
    >
      <Icon className="w-3 h-3 mr-1.5" />
      {label}
      {count > 0 && (
        <Badge className="ml-1.5 rounded-sm text-[9px] bg-[#13151A] text-[#E1E7EF] border-[#2D333B] h-4 px-1">
          {count}
        </Badge>
      )}
    </TabsTrigger>
  );
}

function StatBox({ label, value, color, icon: Icon }) {
  return (
    <div
      className="rounded-sm p-2 border"
      style={{
        borderColor: `${color}40`,
        background: value > 0 ? `linear-gradient(135deg, ${color}15, transparent)` : "#0D0F14",
      }}
    >
      <div className="flex items-center justify-between">
        <span className="text-[9px] font-chivo font-bold uppercase tracking-wider" style={{ color }}>
          {label}
        </span>
        {Icon && <Icon className="w-3 h-3" style={{ color, opacity: value > 0 ? 1 : 0.25 }} />}
      </div>
      <div className="text-2xl font-chivo font-bold mt-1" style={{ color }}>
        {value || 0}
      </div>
      <div className="text-[9px] text-[#6E7681]">shared across cases</div>
    </div>
  );
}

function SharedEntityList({ items, label }) {
  if (!items || items.length === 0) {
    return (
      <p className="text-xs text-[#6E7681] text-center py-8">
        No shared {label}s detected across the selected cases.
      </p>
    );
  }
  return (
    <ScrollArea className="max-h-[60vh]">
      <div className="space-y-1.5 pr-2">
        {items.map((it, i) => (
          <div key={i} className="bg-[#0D0F14] border border-[#2D333B] rounded-sm overflow-hidden" data-testid="shared-entity-row">
            <div
              className="px-2 py-1.5 flex items-center gap-2 border-b border-[#2D333B]"
              style={{ background: it.case_count >= 3 ? "#E63946/10" : "transparent" }}
            >
              <span className="font-mono text-xs text-[#E1E7EF]">{it.value}</span>
              <Badge className="rounded-sm text-[9px] bg-[#0047FF]/20 text-[#0047FF] border-[#0047FF]/40 ml-auto">
                {it.case_count} CASES
              </Badge>
            </div>
            <div className="p-2 space-y-1">
              {it.occurrences.map((o, j) => (
                <div key={j} className="flex items-center gap-2 text-[10px]">
                  <ChevronRight className="w-2.5 h-2.5 text-[#6E7681]" />
                  <span className="text-[#E1E7EF] font-medium">{o.case_name}</span>
                  <span className="text-[#6E7681]">·</span>
                  <span className="text-[#8B949E]">
                    subjects: <span className="font-mono text-[#0047FF]">{o.subjects.join(", ") || "—"}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}

function AliasList({ items }) {
  if (!items || items.length === 0) {
    return (
      <p className="text-xs text-[#6E7681] text-center py-8">
        No subject-name alias matches detected.
      </p>
    );
  }
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] text-[#6E7681] mb-2">
        Subjects from different cases whose names match closely — same person under different spellings?
      </p>
      <ScrollArea className="max-h-[55vh]">
        <div className="space-y-1.5 pr-2">
          {items.map((a, i) => {
            const color = strengthColor(a.match_strength);
            return (
              <div
                key={i}
                className="rounded-sm border bg-[#0D0F14] overflow-hidden"
                style={{ borderColor: `${color}30` }}
                data-testid="alias-row"
              >
                <div className="flex items-stretch">
                  <div className="w-1 flex-shrink-0" style={{ background: color }} />
                  <div className="flex-1 p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge
                        className="rounded-sm text-[9px] font-bold px-1.5 py-0 h-4"
                        style={{ background: `${color}20`, color, borderColor: `${color}40` }}
                      >
                        {a.match_strength}
                      </Badge>
                      <span className="text-[10px] font-mono ml-auto" style={{ color }}>
                        similarity {a.similarity}
                      </span>
                    </div>
                    <div className="text-[11px] text-[#E1E7EF] flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="font-mono font-medium">{a.name1}</span>
                      <span className="text-[#6E7681] text-[9px]">({a.case1_name})</span>
                      <span className="text-[#2D333B]">↔</span>
                      <span className="font-mono font-medium">{a.name2}</span>
                      <span className="text-[#6E7681] text-[9px]">({a.case2_name})</span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
