import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  MessageCircle, Upload, Trash2, RotateCcw, RefreshCw, AlertTriangle,
  FileText, Loader2, Users, Phone, Mail, Link as LinkIcon, DollarSign,
  MapPin, Clock, Eye, Image as ImageIcon, Mic, Video, FileQuestion, ShieldAlert,
  Hash,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function WhatsAppTab({ caseId, caseData }) {
  const [uploads, setUploads] = useState([]);
  const [active, setActive] = useState(null);          // upload_id whose analysis is shown
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [tick, setTick] = useState(0);
  const fileInputRef = useRef(null);
  const reuploadInputRef = useRef(null);
  const reuploadTargetRef = useRef(null);

  const fetchUploads = async () => {
    try {
      const res = await axios.get(`${API}/cases/${caseId}/whatsapp/uploads`);
      setUploads(res.data);
      if (!active && res.data.length > 0) {
        const firstActive = res.data.find((u) => !u.is_deleted);
        if (firstActive) loadAnalysis(firstActive.id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { fetchUploads(); }, [caseId]);

  // Countdown ticker for soft-deleted items
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    if (uploads.some((u) => u.is_deleted)) {
      const now = Date.now();
      if (uploads.some((u) => u.is_deleted && u.deletion_expires_at &&
        new Date(u.deletion_expires_at).getTime() <= now &&
        new Date(u.deletion_expires_at).getTime() > now - 2000)) {
        fetchUploads();
      }
    }
  }, [tick, uploads]);

  const loadAnalysis = async (uploadId) => {
    setActive(uploadId);
    setLoading(true);
    try {
      const res = await axios.get(`${API}/cases/${caseId}/whatsapp/uploads/${uploadId}/analysis`);
      setAnalysis(res.data);
    } catch (e) {
      toast.error("Failed to load analysis");
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip") && !file.name.toLowerCase().endsWith(".txt")) {
      toast.error("Only .zip or .txt WhatsApp exports are supported");
      return;
    }
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await axios.post(`${API}/cases/${caseId}/whatsapp/upload`, fd);
      toast.success(
        `Parsed: ${res.data.upload.message_count} messages, ` +
        `${res.data.upload.attachment_count} attachments`
      );
      await fetchUploads();
      loadAnalysis(res.data.upload.id);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const deleteUpload = async (uploadId, fileName) => {
    if (!window.confirm(`Delete "${fileName}"? You'll have 3 minutes to undo.`)) return;
    try {
      await axios.delete(`${API}/cases/${caseId}/whatsapp/uploads/${uploadId}`);
      toast.success("Deleted — undo available for 3 minutes", {
        action: { label: "Undo", onClick: () => undoDelete(uploadId) },
        duration: 8000,
      });
      if (active === uploadId) { setActive(null); setAnalysis(null); }
      fetchUploads();
    } catch (e) {
      toast.error("Delete failed");
    }
  };

  const undoDelete = async (uploadId) => {
    try {
      await axios.post(`${API}/cases/${caseId}/whatsapp/uploads/${uploadId}/undo`);
      toast.success("Restored");
      fetchUploads();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Undo failed");
    }
  };

  const triggerReupload = (uploadId) => {
    reuploadTargetRef.current = uploadId;
    reuploadInputRef.current?.click();
  };

  const handleReupload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    const target = reuploadTargetRef.current;
    reuploadTargetRef.current = null;
    if (!file || !target) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await axios.post(`${API}/cases/${caseId}/whatsapp/uploads/${target}/reupload`, fd);
      toast.success("Replaced — original kept for undo for 3 minutes", {
        action: { label: "Undo", onClick: () => undoDelete(target) },
        duration: 8000,
      });
      fetchUploads();
      loadAnalysis(res.data.new_upload.id);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Reupload failed");
    }
  };

  return (
    <div data-testid="whatsapp-tab" className="space-y-4">
      <input type="file" ref={fileInputRef} className="hidden" accept=".zip,.txt"
        onChange={handleUpload} data-testid="whatsapp-file-input" />
      <input type="file" ref={reuploadInputRef} className="hidden" accept=".zip,.txt"
        onChange={handleReupload} data-testid="whatsapp-reupload-input" />

      {/* Phase 1 disclosure banner */}
      <div className="flex items-start gap-2 p-2 bg-[#0047FF]/5 border border-[#0047FF]/30 rounded-sm">
        <MessageCircle className="w-3.5 h-3.5 text-[#0047FF] mt-0.5 shrink-0" />
        <div className="text-[10px] text-[#8B949E] leading-relaxed">
          <span className="text-[#E1E7EF] font-medium">WhatsApp Analysis · Phase 1 (Investigative Triage):</span>{" "}
          Parses chat exports, extracts entities, builds timeline and relationship graph, OCRs image attachments.{" "}
          <span className="text-[#F59E0B]">Voice notes are flagged for manual review.</span>{" "}
          <span className="text-[#F59E0B]">Translation, voice transcription, intent classification — not in Phase 1.</span>{" "}
          Deleted messages cannot be recovered from a ZIP export — only the marker is preserved.{" "}
          <span className="text-[#6E7681] italic">Not for court submission.</span>
        </div>
      </div>

      {/* Uploads strip */}
      <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-chivo text-[#E1E7EF] flex items-center gap-2">
            <Upload className="w-3.5 h-3.5 text-[#0047FF]" />
            WhatsApp Exports ({uploads.filter((u) => !u.is_deleted).length})
            <Button
              data-testid="whatsapp-upload-btn"
              size="sm"
              className="h-7 text-[10px] ml-auto bg-[#0047FF] hover:bg-[#003BD6] text-white rounded-sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? <><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Parsing...</>
                         : <><Upload className="w-3 h-3 mr-1" /> Upload .zip / .txt</>}
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {uploads.length === 0 ? (
            <p className="text-xs text-[#6E7681] text-center py-4">
              No WhatsApp exports uploaded yet. Drop a .zip from WhatsApp's "Email chat" feature.
            </p>
          ) : (
            <div className="space-y-1.5">
              {uploads.map((u, i) => (
                <WAUploadRow
                  key={u.id} upload={u} index={i}
                  isActive={u.id === active}
                  onView={() => !u.is_deleted && loadAnalysis(u.id)}
                  onDelete={() => deleteUpload(u.id, u.file_name)}
                  onUndo={() => undoDelete(u.id)}
                  onReupload={() => triggerReupload(u.id)}
                  tickKey={tick}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Analysis view */}
      {loading && (
        <div className="text-center py-12 text-[#8B949E] text-xs">
          <Loader2 className="w-5 h-5 mx-auto mb-2 animate-spin text-[#0047FF]" />
          Loading analysis…
        </div>
      )}
      {analysis && !loading && (
        <WhatsAppAnalysisView analysis={analysis} caseId={caseId} uploadId={active} />
      )}
    </div>
  );
}

function WAUploadRow({ upload, index, isActive, onView, onDelete, onUndo, onReupload, tickKey }) {
  const isDeleted = !!upload.is_deleted;
  let remainingMs = 0;
  if (isDeleted && upload.deletion_expires_at) {
    remainingMs = Math.max(0, new Date(upload.deletion_expires_at).getTime() - Date.now());
  }
  const expired = isDeleted && remainingMs <= 0;
  const remainSec = Math.ceil(remainingMs / 1000);
  const remainStr = remainSec >= 60
    ? `${Math.floor(remainSec / 60)}m ${remainSec % 60}s`
    : `${remainSec}s`;

  return (
    <button
      type="button"
      data-testid={`whatsapp-upload-row-${index}`}
      disabled={isDeleted}
      onClick={onView}
      className={`w-full text-left p-2 rounded-sm border transition-colors ${
        isDeleted
          ? "bg-[#E63946]/5 border-[#E63946]/30 cursor-not-allowed"
          : isActive
          ? "bg-[#0047FF]/15 border-[#0047FF]/50"
          : "bg-[#0D0F14] border-[#2D333B] hover:bg-[#13151A]"
      }`}
    >
      <div className="flex items-center gap-2">
        <FileText className={`w-3 h-3 shrink-0 ${isDeleted ? "text-[#E63946]" : "text-[#10B981]"}`} />
        <span className={`text-xs truncate flex-1 ${isDeleted ? "text-[#8B949E] line-through" : "text-[#E1E7EF]"}`}>
          {upload.file_name}
        </span>
        {!isDeleted && (
          <div className="flex items-center gap-0.5 shrink-0">
            <Button
              data-testid={`whatsapp-reupload-${index}`}
              variant="ghost" size="sm"
              onClick={(e) => { e.stopPropagation(); onReupload(); }}
              title="Replace"
              className="h-5 w-5 p-0 text-[#6E7681] hover:text-[#0047FF]"
            ><RefreshCw className="w-3 h-3" /></Button>
            <Button
              data-testid={`whatsapp-delete-${index}`}
              variant="ghost" size="sm"
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              title="Delete"
              className="h-5 w-5 p-0 text-[#6E7681] hover:text-[#E63946]"
            ><Trash2 className="w-3 h-3" /></Button>
          </div>
        )}
        {isDeleted && !expired && (
          <Button
            data-testid={`whatsapp-undo-${index}`}
            variant="ghost" size="sm"
            onClick={(e) => { e.stopPropagation(); onUndo(); }}
            className="h-6 px-2 text-[10px] text-[#10B981] hover:bg-[#10B981]/10 rounded-sm"
          ><RotateCcw className="w-3 h-3 mr-1" /> Undo</Button>
        )}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[10px] text-[#6E7681]">
        <span><Users className="inline w-2.5 h-2.5 mr-0.5" />{upload.participants?.length || 0} participants</span>
        <span className="font-mono">{upload.message_count} msgs</span>
        <span className="font-mono">{upload.attachment_count} attach</span>
        {isDeleted && !expired && (
          <span className="ml-auto font-mono text-[#F59E0B]">
            <AlertTriangle className="inline w-2.5 h-2.5 mr-0.5" />
            {upload.deletion_reason === "replaced" ? "Replaced" : "Deleted"} · undo in {remainStr}
          </span>
        )}
      </div>
      <span className="hidden">{tickKey}</span>
    </button>
  );
}

function WhatsAppAnalysisView({ analysis, caseId, uploadId }) {
  const a = analysis.analysis;
  const overview = a.overview || {};
  return (
    <Tabs defaultValue="overview" className="w-full">
      <TabsList className="bg-[#13151A] border border-[#2D333B] rounded-sm">
        <TabsTrigger value="overview" data-testid="wa-tab-overview" className="text-xs rounded-sm data-[state=active]:bg-[#0047FF] data-[state=active]:text-white">Overview</TabsTrigger>
        <TabsTrigger value="messages" data-testid="wa-tab-messages" className="text-xs rounded-sm data-[state=active]:bg-[#0047FF] data-[state=active]:text-white">Messages ({analysis.messages?.length || 0})</TabsTrigger>
        <TabsTrigger value="entities" data-testid="wa-tab-entities" className="text-xs rounded-sm data-[state=active]:bg-[#0047FF] data-[state=active]:text-white">Entities</TabsTrigger>
        <TabsTrigger value="timeline" data-testid="wa-tab-timeline" className="text-xs rounded-sm data-[state=active]:bg-[#0047FF] data-[state=active]:text-white">Timeline</TabsTrigger>
        <TabsTrigger value="attachments" data-testid="wa-tab-attachments" className="text-xs rounded-sm data-[state=active]:bg-[#0047FF] data-[state=active]:text-white">Attachments ({analysis.attachments?.length || 0})</TabsTrigger>
        <TabsTrigger value="indicators" data-testid="wa-tab-indicators" className="text-xs rounded-sm data-[state=active]:bg-[#0047FF] data-[state=active]:text-white">Indicators ({a.indicators?.length || 0})</TabsTrigger>
      </TabsList>

      <TabsContent value="overview" className="mt-3">
        <OverviewPanel overview={overview} subjectLinks={a.subject_links} participants={a.per_participant} />
      </TabsContent>
      <TabsContent value="messages" className="mt-3">
        <MessagesPanel messages={analysis.messages || []} participants={analysis.upload?.participants || []} />
      </TabsContent>
      <TabsContent value="entities" className="mt-3">
        <EntitiesPanel entities={a.entities} />
      </TabsContent>
      <TabsContent value="timeline" className="mt-3">
        <TimelinePanel heatmap={a.heatmap} silentPeriods={a.silent_periods} />
      </TabsContent>
      <TabsContent value="attachments" className="mt-3">
        <AttachmentsPanel attachments={analysis.attachments || []} caseId={caseId} uploadId={uploadId} attSummary={a.attachment_summary} />
      </TabsContent>
      <TabsContent value="indicators" className="mt-3">
        <IndicatorsPanel indicators={a.indicators || []} reviewQueue={a.media_review_queue || []} />
      </TabsContent>
    </Tabs>
  );
}

function OverviewPanel({ overview, subjectLinks, participants }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Stat label="Messages" value={overview.total_messages} icon={MessageCircle} color="#10B981" />
        <Stat label="Participants" value={overview.total_participants} icon={Users} color="#0047FF" />
        <Stat label="Attachments" value={overview.total_attachments} icon={ImageIcon} color="#F59E0B" />
        <Stat label="Days Span" value={overview.duration_days} icon={Clock} color="#A78BFA" />
      </div>

      {(subjectLinks?.by_phone?.length > 0 || subjectLinks?.by_name?.length > 0) && (
        <Card className="bg-[#13151A] border-[#10B981]/30 rounded-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-chivo text-[#10B981] flex items-center gap-2">
              <ShieldAlert className="w-3 h-3" /> Cross-Correlation with Case Subjects
            </CardTitle>
          </CardHeader>
          <CardContent>
            {subjectLinks.by_phone.map((l, i) => (
              <div key={`p${i}`} className="text-[11px] text-[#E1E7EF] p-1.5 bg-[#0D0F14] rounded-sm mb-1">
                <span className="text-[#10B981] font-medium">Phone match:</span> {l.inference}
              </div>
            ))}
            {subjectLinks.by_name.map((l, i) => (
              <div key={`n${i}`} className="text-[11px] text-[#E1E7EF] p-1.5 bg-[#0D0F14] rounded-sm mb-1">
                <span className="text-[#10B981] font-medium">Name match:</span> {l.inference}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-chivo text-[#E1E7EF]">Per-Participant Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-1">
            {Object.entries(participants || {}).map(([name, s]) => (
              <div key={name} className="flex items-center gap-2 text-[10px] p-1.5 bg-[#0D0F14] rounded-sm" data-testid="wa-participant-row">
                <span className="text-[#E1E7EF] font-medium w-32 truncate">{name}</span>
                <span className="font-mono text-[#0047FF]">{s.total_messages}</span>
                <span className="text-[#6E7681]">msgs ·</span>
                <span className="font-mono text-[#10B981]">{s.text_messages}</span>
                <span className="text-[#6E7681]">text ·</span>
                <span className="font-mono text-[#F59E0B]">{s.media_messages}</span>
                <span className="text-[#6E7681]">media ·</span>
                <span className="font-mono text-[#E63946]">{s.deleted_count}</span>
                <span className="text-[#6E7681]">del</span>
                <span className="ml-auto text-[#6E7681] font-mono">{Math.round(s.avg_msg_length)} ch avg</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {overview.first_message_ts && (
        <div className="text-[10px] text-[#6E7681] flex gap-4 px-1">
          <span>Span: <span className="font-mono text-[#8B949E]">{overview.first_message_ts.slice(0, 16)}</span> → <span className="font-mono text-[#8B949E]">{overview.last_message_ts.slice(0, 16)}</span></span>
          {overview.unparseable_lines > 0 && (
            <span className="text-[#F59E0B]">⚠ {overview.unparseable_lines} unparseable lines</span>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, icon: Icon, color }) {
  return (
    <div className="rounded-sm p-2 border bg-[#13151A]" style={{ borderColor: `${color}40` }}>
      <div className="flex items-center justify-between">
        <span className="text-[9px] font-chivo font-bold uppercase tracking-wider" style={{ color }}>{label}</span>
        <Icon className="w-3 h-3" style={{ color }} />
      </div>
      <div className="text-xl font-chivo font-bold mt-1" style={{ color }}>{value ?? 0}</div>
    </div>
  );
}

function MessagesPanel({ messages, participants }) {
  const [filter, setFilter] = useState("");
  const filtered = filter
    ? messages.filter((m) => (m.body || "").toLowerCase().includes(filter.toLowerCase()) ||
                              (m.sender || "").toLowerCase().includes(filter.toLowerCase()))
    : messages;
  const colorBySender = {};
  participants.forEach((p, i) => {
    colorBySender[p] = ["#0047FF", "#10B981", "#F59E0B", "#A78BFA", "#06B6D4", "#E63946"][i % 6];
  });
  return (
    <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-chivo text-[#E1E7EF] flex items-center gap-2">
          Messages ({filtered.length})
          <input
            data-testid="wa-message-search"
            type="text" placeholder="Search…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="ml-auto bg-[#0D0F14] border border-[#2D333B] rounded-sm text-[10px] px-2 py-1 text-[#E1E7EF] w-48 focus:outline-none focus:border-[#0047FF]"
          />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[480px]">
          <div className="space-y-1 pr-2">
            {filtered.slice(0, 500).map((m, i) => (
              <MessageRow key={i} m={m} senderColor={colorBySender[m.sender] || "#6E7681"} />
            ))}
            {filtered.length > 500 && (
              <p className="text-[10px] text-[#6E7681] text-center py-2">
                Showing first 500 of {filtered.length}. Use search to narrow.
              </p>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function MessageRow({ m, senderColor }) {
  const kindStyle = {
    text: "",
    media: "italic text-[#A78BFA]",
    deleted: "italic text-[#E63946] line-through",
    system: "italic text-[#6E7681]",
    call: "italic text-[#F59E0B]",
  }[m.kind] || "";
  return (
    <div className="p-1.5 bg-[#0D0F14] rounded-sm border border-[#2D333B] text-[10px]" data-testid="wa-message-row">
      <div className="flex items-center gap-2 mb-0.5">
        {m.sender ? (
          <span className="font-medium font-mono" style={{ color: senderColor }}>{m.sender}</span>
        ) : (
          <span className="text-[#6E7681] italic">[system]</span>
        )}
        <span className="text-[#6E7681] font-mono text-[9px]">{m.local_time_str}</span>
        {m.kind !== "text" && (
          <Badge className="rounded-sm text-[9px] bg-[#2D333B]/30 text-[#8B949E] border-[#2D333B] h-4">{m.kind}</Badge>
        )}
      </div>
      <div className={`text-[#E1E7EF] whitespace-pre-wrap break-words ${kindStyle}`}>
        {m.body || (m.kind === "media" ? "(media)" : "")}
        {m.attachment_filename && <span className="text-[#8B949E] ml-1">→ {m.attachment_filename}</span>}
      </div>
    </div>
  );
}

function EntitiesPanel({ entities }) {
  if (!entities) return null;
  const groups = [
    { key: "phones", label: "Phones", icon: Phone, color: "#10B981" },
    { key: "emails", label: "Emails", icon: Mail, color: "#06B6D4" },
    { key: "urls", label: "URLs", icon: LinkIcon, color: "#A78BFA" },
    { key: "amounts", label: "Money", icon: DollarSign, color: "#F59E0B" },
    { key: "places", label: "Places", icon: MapPin, color: "#E63946" },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {groups.map(({ key, label, icon: Icon, color }) => (
        <Card key={key} className="bg-[#13151A] border-[#2D333B] rounded-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-chivo text-[#E1E7EF] flex items-center gap-2">
              <Icon className="w-3 h-3" style={{ color }} />
              {label} ({entities[key]?.length || 0})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {entities[key]?.length === 0 ? (
              <p className="text-[10px] text-[#6E7681] py-2">None detected</p>
            ) : (
              <ScrollArea className="max-h-48">
                <div className="space-y-1 pr-2">
                  {entities[key].slice(0, 30).map((e, i) => (
                    <div key={i} className="flex items-center gap-2 text-[10px] p-1 bg-[#0D0F14] rounded-sm" data-testid={`wa-entity-${key}-row`}>
                      <span className="font-mono text-[#E1E7EF] truncate flex-1">{e.value}</span>
                      <Badge className="rounded-sm text-[9px] bg-[#2D333B] text-[#8B949E] border-[#2D333B] h-4">{e.count}×</Badge>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function TimelinePanel({ heatmap, silentPeriods }) {
  if (!heatmap) return null;
  const max = Math.max(...heatmap.matrix.flat(), 1);
  return (
    <div className="space-y-3">
      <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-chivo text-[#E1E7EF]">Activity Heatmap (Day × Hour)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-[auto_repeat(24,minmax(0,1fr))] gap-0.5 text-[9px]">
            <div></div>
            {Array.from({ length: 24 }).map((_, h) => (
              <div key={h} className="text-center text-[#6E7681] font-mono">{h}</div>
            ))}
            {heatmap.matrix.map((row, di) => (
              <>
                <div key={`l${di}`} className="text-[#8B949E] pr-1 font-mono">{heatmap.row_labels[di]}</div>
                {row.map((cnt, hi) => {
                  const intensity = cnt / max;
                  return (
                    <div
                      key={`${di}-${hi}`}
                      title={`${heatmap.row_labels[di]} ${hi}:00 — ${cnt} msgs`}
                      data-testid={`wa-heat-${di}-${hi}`}
                      style={{
                        background: cnt === 0 ? "#13151A" : `rgba(0, 71, 255, ${0.2 + intensity * 0.8})`,
                        height: 14,
                      }}
                      className="rounded-[1px] border border-[#2D333B]"
                    />
                  );
                })}
              </>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-chivo text-[#E1E7EF]">Silent Periods (≥ 24h gaps)</CardTitle>
        </CardHeader>
        <CardContent>
          {silentPeriods?.length === 0 ? (
            <p className="text-[10px] text-[#6E7681] py-2">No silent periods longer than 24 hours.</p>
          ) : (
            <div className="space-y-1">
              {silentPeriods?.slice(0, 10).map((sp, i) => (
                <div key={i} className="flex items-center gap-2 text-[10px] p-1.5 bg-[#0D0F14] rounded-sm" data-testid="wa-silent-row">
                  <Clock className="w-3 h-3 text-[#A78BFA] shrink-0" />
                  <span className="font-mono text-[#A78BFA]">{sp.duration_hours.toFixed(1)}h</span>
                  <span className="text-[#6E7681]">·</span>
                  <span className="font-mono text-[#8B949E]">{sp.start_ts.slice(0, 16).replace("T", " ")}</span>
                  <span className="text-[#2D333B]">→</span>
                  <span className="font-mono text-[#8B949E]">{sp.end_ts.slice(0, 16).replace("T", " ")}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function AttachmentsPanel({ attachments, caseId, uploadId, attSummary }) {
  const [filter, setFilter] = useState("all");
  const filtered = filter === "all" ? attachments : attachments.filter((a) => a.mime_hint === filter);
  return (
    <div className="space-y-3">
      <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
        <CardContent className="p-3">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-[10px]">
            <FilterTab label="All" count={attachments.length} active={filter === "all"} onClick={() => setFilter("all")} testId="wa-att-filter-all" />
            <FilterTab label="Images" count={attSummary?.by_kind?.image || 0} active={filter === "image"} onClick={() => setFilter("image")} testId="wa-att-filter-image" />
            <FilterTab label="Voice" count={attSummary?.by_kind?.audio || 0} active={filter === "audio"} onClick={() => setFilter("audio")} testId="wa-att-filter-audio" />
            <FilterTab label="Video" count={attSummary?.by_kind?.video || 0} active={filter === "video"} onClick={() => setFilter("video")} testId="wa-att-filter-video" />
            <FilterTab label="Docs" count={attSummary?.by_kind?.document || 0} active={filter === "document"} onClick={() => setFilter("document")} testId="wa-att-filter-document" />
          </div>
          {attSummary?.duplicates?.length > 0 && (
            <div className="mt-2 text-[10px] text-[#F59E0B] flex items-center gap-1">
              <Hash className="w-3 h-3" />
              {attSummary.duplicates.length} duplicate group(s) detected via perceptual hash
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
        {filtered.map((a, i) => (
          <AttachmentCard key={i} a={a} caseId={caseId} uploadId={uploadId} />
        ))}
      </div>
    </div>
  );
}

function FilterTab({ label, count, active, onClick, testId }) {
  return (
    <button
      type="button" onClick={onClick} data-testid={testId}
      className={`p-1.5 rounded-sm border transition-colors ${active ? "bg-[#0047FF]/15 border-[#0047FF]/50 text-[#0047FF]" : "bg-[#0D0F14] border-[#2D333B] text-[#8B949E] hover:text-[#E1E7EF]"}`}
    >
      <span className="font-medium">{label}</span> <span className="font-mono">({count})</span>
    </button>
  );
}

function AttachmentCard({ a, caseId, uploadId }) {
  const url = `${BACKEND_URL}/api/cases/${caseId}/whatsapp/uploads/${uploadId}/attachments/${encodeURIComponent(a.filename.split("/").pop())}`;
  const Icon = a.mime_hint === "image" ? ImageIcon :
               a.mime_hint === "audio" ? Mic :
               a.mime_hint === "video" ? Video :
               a.mime_hint === "document" ? FileText : FileQuestion;
  return (
    <Card className="bg-[#13151A] border-[#2D333B] rounded-sm overflow-hidden" data-testid="wa-attachment-card">
      {a.mime_hint === "image" ? (
        <img src={url} alt={a.filename} className="w-full h-40 object-cover bg-[#0D0F14]" loading="lazy" />
      ) : (
        <div className="w-full h-32 flex items-center justify-center bg-[#0D0F14]">
          <Icon className="w-10 h-10 text-[#2D333B]" />
        </div>
      )}
      <div className="p-2 text-[10px]">
        <div className="text-[#E1E7EF] font-mono truncate">{a.filename}</div>
        <div className="text-[#6E7681] flex flex-wrap gap-2 mt-1">
          <span>{(a.size_bytes / 1024).toFixed(1)} KB</span>
          {a.perceptual_hash && <span title="Perceptual hash">phash: {a.perceptual_hash.slice(0, 8)}</span>}
          {a.exif_present ? (
            <Badge className="rounded-sm text-[9px] bg-[#10B981]/15 text-[#10B981] border-[#10B981]/40">EXIF</Badge>
          ) : a.mime_hint === "image" && (
            <Badge className="rounded-sm text-[9px] bg-[#6E7681]/15 text-[#6E7681] border-[#2D333B]" title="WhatsApp strips EXIF on send">no EXIF</Badge>
          )}
          {a.needs_manual_review && (
            <Badge className="rounded-sm text-[9px] bg-[#F59E0B]/15 text-[#F59E0B] border-[#F59E0B]/40">manual review</Badge>
          )}
        </div>
        {a.ocr_text && (
          <details className="mt-1">
            <summary className="text-[#0047FF] cursor-pointer text-[10px]">OCR text ({a.ocr_text.length} chars)</summary>
            <pre className="mt-1 p-1 bg-[#0D0F14] rounded-sm text-[9px] text-[#8B949E] whitespace-pre-wrap break-words max-h-32 overflow-auto">{a.ocr_text}</pre>
          </details>
        )}
        {a.review_reason && (
          <div className="mt-1 text-[#F59E0B] italic">{a.review_reason}</div>
        )}
      </div>
    </Card>
  );
}

function IndicatorsPanel({ indicators, reviewQueue }) {
  const sevColor = (s) => ({ LOW: "#FBBF24", MEDIUM: "#F59E0B", HIGH: "#E63946" }[s] || "#8B949E");
  return (
    <div className="space-y-3">
      <Card className="bg-[#13151A] border-[#F59E0B]/30 rounded-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-chivo text-[#F59E0B] flex items-center gap-2">
            <AlertTriangle className="w-3 h-3" /> Rule-Based Indicators (low confidence, review required)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {indicators.length === 0 ? (
            <p className="text-[10px] text-[#6E7681] py-2">No indicators triggered.</p>
          ) : (
            <div className="space-y-1">
              {indicators.map((ind, i) => (
                <div key={i} className="rounded-sm border bg-[#0D0F14] overflow-hidden" style={{ borderColor: `${sevColor(ind.severity)}30` }} data-testid="wa-indicator-row">
                  <div className="flex items-stretch">
                    <div className="w-1 shrink-0" style={{ background: sevColor(ind.severity) }} />
                    <div className="flex-1 p-2">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge className="rounded-sm text-[9px] font-bold px-1.5 py-0 h-4" style={{ background: `${sevColor(ind.severity)}20`, color: sevColor(ind.severity), borderColor: `${sevColor(ind.severity)}40` }}>{ind.severity}</Badge>
                        <span className="text-[10px] font-mono text-[#8B949E]">{ind.tag}</span>
                      </div>
                      <div className="text-[11px] text-[#E1E7EF] font-medium">{ind.title}</div>
                      <div className="text-[10px] text-[#8B949E] mt-0.5">{ind.detail}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {reviewQueue.length > 0 && (
        <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-chivo text-[#E1E7EF] flex items-center gap-2">
              <Eye className="w-3 h-3 text-[#A78BFA]" /> Manual Review Queue ({reviewQueue.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {reviewQueue.map((r, i) => (
                <div key={i} className="flex items-center gap-2 text-[10px] p-1.5 bg-[#0D0F14] rounded-sm">
                  <Mic className="w-3 h-3 text-[#A78BFA]" />
                  <span className="font-mono text-[#E1E7EF] flex-1 truncate">{r.filename}</span>
                  <span className="text-[#6E7681]">{r.reason}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
