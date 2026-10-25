import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import {
  ArrowLeft, Plus, Trash2, Upload, Play, Download, FileText,
  User, MapPin, Smartphone, Phone, Loader2, CheckCircle2, AlertTriangle,
  RotateCcw, RefreshCw, History,
} from "lucide-react";
import AnalysisReport from "@/components/AnalysisReport";
import WhatsAppTab from "@/components/WhatsAppTab";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function CaseView() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [caseData, setCaseData] = useState(null);
  const [uploads, setUploads] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadQuality, setUploadQuality] = useState(null);
  const [tab, setTab] = useState("overview");

  // Subject form
  const [newSubject, setNewSubject] = useState({ name: "" });
  // Upload form
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadSubject, setUploadSubject] = useState("");
  const [uploadType, setUploadType] = useState("ipdr");
  const [uploadPassword, setUploadPassword] = useState("");
  const [rememberPassword, setRememberPassword] = useState(false);

  const fetchCase = useCallback(async () => {
    try {
      const [caseRes, uploadsRes] = await Promise.all([
        axios.get(`${API}/cases/${caseId}`),
        axios.get(`${API}/cases/${caseId}/uploads`),
      ]);
      setCaseData(caseRes.data);
      setUploads(uploadsRes.data);
      try {
        const analysisRes = await axios.get(`${API}/cases/${caseId}/analysis`);
        setAnalysis(analysisRes.data);
      } catch {
        setAnalysis(null);
      }
    } catch {
      toast.error("Failed to load case");
      navigate("/");
    } finally {
      setLoading(false);
    }
  }, [caseId, navigate]);

  useEffect(() => { fetchCase(); }, [fetchCase]);

  const addSubject = async () => {
    if (!newSubject.name.trim()) { toast.error("Subject name required"); return; }
    try {
      await axios.post(`${API}/cases/${caseId}/subjects`, newSubject);
      toast.success(`Subject "${newSubject.name}" added`);
      setNewSubject({ name: "" });
      fetchCase();
    } catch (e) {
      toast.error("Failed to add subject");
    }
  };

  const removeSubject = async (name) => {
    try {
      await axios.delete(`${API}/cases/${caseId}/subjects/${encodeURIComponent(name)}`);
      toast.success(`Subject "${name}" removed`);
      fetchCase();
    } catch (e) {
      toast.error("Failed to remove subject");
    }
  };

  const handleUpload = async () => {
    if (!uploadFile || !uploadSubject) { toast.error("Select a file and subject"); return; }
    setUploading(true);
    const formData = new FormData();
    formData.append("file", uploadFile);
    formData.append("subject_name", uploadSubject);
    formData.append("data_type", uploadType);
    if (uploadPassword) formData.append("password", uploadPassword);
    try {
      const res = await axios.post(`${API}/cases/${caseId}/upload`, formData);
      toast.success(`Parsed ${res.data.records_parsed} records from ${uploadFile.name}`);
      if (res.data.quality_report) setUploadQuality(res.data.quality_report);
      setUploadFile(null);
      if (!rememberPassword) setUploadPassword("");
      fetchCase();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const deleteUpload = async (uploadId, fileName) => {
    if (!window.confirm(`Delete "${fileName}"? You'll have 3 minutes to undo.`)) return;
    try {
      const res = await axios.delete(`${API}/cases/${caseId}/uploads/${uploadId}`);
      toast.success("File deleted — undo available for 3 minutes", {
        action: {
          label: "Undo",
          onClick: () => undoDeleteUpload(uploadId),
        },
        duration: 8000,
      });
      fetchCase();
      return res.data;
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to delete upload");
    }
  };

  const undoDeleteUpload = async (uploadId) => {
    try {
      await axios.post(`${API}/cases/${caseId}/uploads/${uploadId}/undo`);
      toast.success("File restored");
      fetchCase();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Undo window has expired");
    }
  };

  const reuploadHiddenInputRef = useRef(null);
  const [reuploadTargetId, setReuploadTargetId] = useState(null);

  const triggerReupload = (uploadId) => {
    setReuploadTargetId(uploadId);
    reuploadHiddenInputRef.current?.click();
  };

  const handleReuploadFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";  // reset so same file can be picked again
    if (!file || !reuploadTargetId) return;
    const targetId = reuploadTargetId;
    setReuploadTargetId(null);
    const formData = new FormData();
    formData.append("file", file);
    if (uploadPassword) formData.append("password", uploadPassword);
    try {
      await axios.post(`${API}/cases/${caseId}/uploads/${targetId}/reupload`, formData);
      toast.success("File replaced — original kept for undo for 3 minutes", {
        action: { label: "Undo", onClick: () => undoDeleteUpload(targetId) },
        duration: 8000,
      });
      fetchCase();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to replace file");
    }
  };

  // Countdown ticker for soft-deleted items (re-render every second so the
  // "Xm Ys remaining" labels update in real time).
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);
  // Auto-refetch when any soft-delete window expires (so list cleans itself)
  useEffect(() => {
    if (!uploads.some((u) => u.is_deleted)) return;
    const now = Date.now();
    const anyJustExpired = uploads.some(
      (u) => u.is_deleted && u.deletion_expires_at &&
        new Date(u.deletion_expires_at).getTime() <= now &&
        new Date(u.deletion_expires_at).getTime() > now - 2000
    );
    if (anyJustExpired) {
      fetchCase();
    }
  }, [tick, uploads, fetchCase]);

  const runAnalysis = async () => {
    setAnalyzing(true);
    setAnalysisProgress(null);
    try {
      await axios.post(`${API}/cases/${caseId}/analyze`);
      // Start polling for progress
      const pollInterval = setInterval(async () => {
        try {
          const statusRes = await axios.get(`${API}/cases/${caseId}/analyze/status`);
          const job = statusRes.data;
          setAnalysisProgress(job);
          if (job.status === "complete") {
            clearInterval(pollInterval);
            const analysisRes = await axios.get(`${API}/cases/${caseId}/analysis`);
            setAnalysis(analysisRes.data);
            setAnalyzing(false);
            toast.success("Analysis complete");
            setTab("analysis");
            fetchCase();
          } else if (job.status === "failed") {
            clearInterval(pollInterval);
            setAnalyzing(false);
            toast.error(job.message || "Analysis failed");
          }
        } catch {
          // Keep polling on transient errors
        }
      }, 2000);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to start analysis");
      setAnalyzing(false);
    }
  };

  const downloadReport = (fmt) => {
    window.open(`${API}/cases/${caseId}/report/${fmt}`, "_blank");
  };

  if (loading) return <div className="p-6 text-[#6E7681]">Loading case...</div>;
  if (!caseData) return null;

  return (
    <div data-testid="case-view-page" className="p-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <Button data-testid="back-btn" variant="ghost" size="sm" onClick={() => navigate("/")} className="text-[#8B949E] hover:text-[#E1E7EF] rounded-sm px-2">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div className="flex-1">
          <h1 data-testid="case-title" className="text-2xl font-bold text-[#E1E7EF] font-chivo tracking-tight">{caseData.name}</h1>
          <p className="text-xs text-[#6E7681] mt-0.5">{caseData.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge className="rounded-sm text-[10px] bg-[#0047FF]/15 text-[#0047FF] border-[#0047FF]/30">
            {caseData.status?.replace("_", " ").toUpperCase()}
          </Badge>
          <span className="text-xs font-mono text-[#6E7681]">{(caseData.record_count || 0).toLocaleString()} records</span>
        </div>
      </div>

      {/* Re-analysis warning banner — persistent until next analysis run completes */}
      {caseData.needs_reanalysis && (
        <div
          data-testid="reanalysis-banner"
          className="mb-4 flex items-center gap-2 px-3 py-2 bg-[#F59E0B]/10 border border-[#F59E0B]/40 rounded-sm"
        >
          <AlertTriangle className="w-3.5 h-3.5 text-[#F59E0B] shrink-0" />
          <span className="text-[11px] text-[#E1E7EF] flex-1">
            <span className="font-medium text-[#F59E0B]">Data changed since last analysis.</span>
            <span className="text-[#8B949E]"> Run analysis again to refresh results.</span>
            {caseData.last_change_reason && (
              <span className="text-[#6E7681] ml-2 font-mono text-[10px]">({caseData.last_change_reason})</span>
            )}
          </span>
          <Button
            data-testid="reanalysis-banner-btn"
            onClick={runAnalysis}
            disabled={analyzing}
            size="sm"
            className="h-6 px-2 text-[10px] bg-[#F59E0B] hover:bg-[#E08E00] text-black rounded-sm"
          >
            {analyzing ? (
              <><Loader2 className="w-2.5 h-2.5 mr-1 animate-spin" /> Running...</>
            ) : (
              <><RefreshCw className="w-2.5 h-2.5 mr-1" /> Run Analysis</>
            )}
          </Button>
        </div>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-[#13151A] border border-[#2D333B] rounded-sm mb-4">
          <TabsTrigger data-testid="tab-overview" value="overview" className="rounded-sm text-xs data-[state=active]:bg-[#0047FF] data-[state=active]:text-white">Overview</TabsTrigger>
          <TabsTrigger data-testid="tab-upload" value="upload" className="rounded-sm text-xs data-[state=active]:bg-[#0047FF] data-[state=active]:text-white">Upload Data</TabsTrigger>
          <TabsTrigger data-testid="tab-analysis" value="analysis" className="rounded-sm text-xs data-[state=active]:bg-[#0047FF] data-[state=active]:text-white">Analysis</TabsTrigger>
          <TabsTrigger data-testid="tab-whatsapp" value="whatsapp" className="rounded-sm text-xs data-[state=active]:bg-[#0047FF] data-[state=active]:text-white">WhatsApp</TabsTrigger>
          <TabsTrigger data-testid="tab-report" value="report" className="rounded-sm text-xs data-[state=active]:bg-[#0047FF] data-[state=active]:text-white">Report</TabsTrigger>
        </TabsList>

        {/* OVERVIEW TAB */}
        <TabsContent value="overview">
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div className="xl:col-span-2">
              <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-chivo text-[#E1E7EF] flex items-center gap-2">
                    <User className="w-4 h-4 text-[#0047FF]" /> Subjects ({caseData.subjects?.length || 0})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {caseData.subjects?.length > 0 ? (
                    <div className="space-y-2">
                      {caseData.subjects.map((s, i) => (
                        <div key={i} className="flex items-center justify-between p-2.5 bg-[#090A0C] border border-[#2D333B] rounded-sm">
                          <div className="flex items-center gap-4">
                            <span className="text-sm font-medium text-[#E1E7EF]">{s.name}</span>
                            {s.phone && <span className="text-xs font-mono text-[#8B949E] flex items-center gap-1"><Phone className="w-3 h-3" />{s.phone}</span>}
                            {s.imei && <span className="text-xs font-mono text-[#8B949E] flex items-center gap-1"><Smartphone className="w-3 h-3" />{s.imei}</span>}
                            {s.location && <span className="text-xs font-mono text-[#8B949E] flex items-center gap-1"><MapPin className="w-3 h-3" />{s.location}</span>}
                          </div>
                          <Button data-testid={`remove-subject-${i}`} variant="ghost" size="sm" className="h-6 px-1.5 text-[#6E7681] hover:text-[#E63946]" onClick={() => removeSubject(s.name)}>
                            <Trash2 className="w-3 h-3" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-[#6E7681] py-4 text-center">No subjects added yet</p>
                  )}
                  <Separator className="my-3 bg-[#2D333B]" />
                  <div className="flex gap-2 items-end">
                    <div className="flex-1">
                      <Input data-testid="subject-name-input" placeholder="Subject Name *" value={newSubject.name} onChange={(e) => setNewSubject({ ...newSubject, name: e.target.value })} className="bg-[#090A0C] border-[#2D333B] text-[#E1E7EF] rounded-sm text-xs" />
                    </div>
                    <Button data-testid="add-subject-btn" onClick={addSubject} className="bg-[#0047FF] hover:bg-[#003BD6] text-white rounded-sm text-xs" size="sm">
                      <Plus className="w-3 h-3 mr-1" /> Add Subject
                    </Button>
                  </div>
                  <p className="text-[10px] text-[#6E7681] mt-1">IMEI, Phone, and Address are auto-extracted from uploaded PDFs</p>
                </CardContent>
              </Card>
            </div>
            <div className="space-y-4">
              <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
                <CardContent className="p-4 space-y-3">
                  <div className="flex justify-between text-xs"><span className="text-[#6E7681]">UPLOADS</span><span className="font-mono text-[#E1E7EF]">{caseData.upload_count || 0}</span></div>
                  <div className="flex justify-between text-xs"><span className="text-[#6E7681]">RECORDS</span><span className="font-mono text-[#E1E7EF]">{(caseData.record_count || 0).toLocaleString()}</span></div>
                  <div className="flex justify-between text-xs"><span className="text-[#6E7681]">STATUS</span><span className="font-mono text-[#0047FF]">{caseData.status?.toUpperCase()}</span></div>
                  <Separator className="bg-[#2D333B]" />
                  <Button data-testid="run-analysis-btn" onClick={runAnalysis} disabled={analyzing || !caseData.record_count} className="w-full bg-[#0047FF] hover:bg-[#003BD6] text-white rounded-sm text-xs" size="sm">
                    {analyzing ? <><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Analyzing...</> : <><Play className="w-3 h-3 mr-1" /> Run Analysis</>}
                  </Button>
                  {analyzing && analysisProgress && (
                    <div className="mt-2 space-y-1">
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="text-[#8B949E]">{analysisProgress.message}</span>
                        <span className="font-mono text-[#0047FF]">{analysisProgress.progress}%</span>
                      </div>
                      <div className="h-1.5 bg-[#2D333B] rounded-full overflow-hidden">
                        <div className="h-full bg-[#0047FF] rounded-full transition-all duration-500" style={{ width: `${analysisProgress.progress}%` }} />
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
              {analysis && (
                <Card className="bg-[#13151A] border-[#10B981]/30 rounded-sm">
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
                      <span className="text-xs font-medium text-[#10B981]">Analysis Complete</span>
                    </div>
                    {analysis.summary?.key_findings?.slice(0, 3).map((f, i) => (
                      <p key={i} className="text-[11px] text-[#8B949E] mt-1">{f}</p>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </TabsContent>

        {/* UPLOAD TAB */}
        <TabsContent value="upload">
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Card className="xl:col-span-2 bg-[#13151A] border-[#2D333B] rounded-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-chivo text-[#E1E7EF] flex items-center gap-2">
                  <Upload className="w-4 h-4 text-[#0047FF]" /> Upload Data File
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {(!caseData.subjects || caseData.subjects.length === 0) ? (
                  <div className="p-6 text-center border border-dashed border-[#2D333B] rounded-sm">
                    <AlertTriangle className="w-6 h-6 text-[#F59E0B] mx-auto mb-2" />
                    <p className="text-xs text-[#8B949E]">Add subjects in the Overview tab before uploading data.</p>
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-[#8B949E] text-xs uppercase tracking-[0.15em]">Subject</Label>
                        <Select value={uploadSubject} onValueChange={setUploadSubject}>
                          <SelectTrigger data-testid="upload-subject-select" className="bg-[#090A0C] border-[#2D333B] text-[#E1E7EF] rounded-sm mt-1">
                            <SelectValue placeholder="Select subject" />
                          </SelectTrigger>
                          <SelectContent className="bg-[#13151A] border-[#2D333B]">
                            {caseData.subjects?.map((s) => (
                              <SelectItem key={s.name} value={s.name} className="text-[#E1E7EF]">{s.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="text-[#8B949E] text-xs uppercase tracking-[0.15em]">Data Type</Label>
                        <Select value={uploadType} onValueChange={setUploadType}>
                          <SelectTrigger data-testid="upload-type-select" className="bg-[#090A0C] border-[#2D333B] text-[#E1E7EF] rounded-sm mt-1">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-[#13151A] border-[#2D333B]">
                            <SelectItem value="ipdr" className="text-[#E1E7EF]">IPDR (Internet)</SelectItem>
                            <SelectItem value="cdr" className="text-[#E1E7EF]">CDR (Call Records)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div>
                      <Label className="text-[#8B949E] text-xs uppercase tracking-[0.15em]">File (CSV, Excel, PDF)</Label>
                      <div className="mt-1 border border-dashed border-[#2D333B] rounded-sm p-4 drop-zone text-center">
                        <input
                          data-testid="file-input"
                          type="file"
                          accept=".csv,.xlsx,.xls,.pdf,.png,.jpg,.jpeg"
                          onChange={(e) => setUploadFile(e.target.files[0])}
                          className="hidden"
                          id="file-upload"
                        />
                        <label htmlFor="file-upload" className="cursor-pointer">
                          <Upload className="w-5 h-5 text-[#6E7681] mx-auto mb-1" />
                          <p className="text-xs text-[#8B949E]">{uploadFile ? uploadFile.name : "Click to select file"}</p>
                          <p className="text-[10px] text-[#6E7681] mt-0.5">CSV, Excel (.xlsx), PDF supported</p>
                        </label>
                      </div>
                    </div>
                    <div>
                      <Label className="text-[#8B949E] text-xs uppercase tracking-[0.15em]">Password (for protected files)</Label>
                      <Input
                        data-testid="upload-password-input"
                        type="password"
                        placeholder="Leave empty if not password-protected"
                        value={uploadPassword}
                        onChange={(e) => setUploadPassword(e.target.value)}
                        className="bg-[#090A0C] border-[#2D333B] text-[#E1E7EF] rounded-sm mt-1"
                      />
                      <label className="flex items-center gap-2 mt-2 cursor-pointer">
                        <input
                          data-testid="remember-password-checkbox"
                          type="checkbox"
                          checked={rememberPassword}
                          onChange={(e) => setRememberPassword(e.target.checked)}
                          className="w-3.5 h-3.5 rounded-sm border-[#2D333B] bg-[#090A0C] accent-[#0047FF]"
                        />
                        <span className="text-[11px] text-[#8B949E]">Remember this password for next upload</span>
                      </label>
                    </div>
                    <Button data-testid="upload-btn" onClick={handleUpload} disabled={uploading || !uploadFile || !uploadSubject} className="bg-[#0047FF] hover:bg-[#003BD6] text-white rounded-sm text-sm">
                      {uploading ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Uploading...</> : <><Upload className="w-4 h-4 mr-1" /> Upload & Parse</>}
                    </Button>
                    {uploadQuality && (
                      <div data-testid="quality-report" className="mt-2 p-2 bg-[#090A0C] border border-[#2D333B] rounded-sm">
                        <div className="flex items-center justify-between text-[10px] mb-1">
                          <span className="text-[#8B949E] uppercase tracking-wider">Data Quality</span>
                          <span className={`font-mono font-bold ${uploadQuality.quality_score >= 90 ? "text-[#10B981]" : uploadQuality.quality_score >= 70 ? "text-[#F59E0B]" : "text-[#E63946]"}`}>
                            {uploadQuality.quality_score}%
                          </span>
                        </div>
                        <div className="flex gap-3 text-[10px] text-[#6E7681]">
                          <span>Valid: <span className="text-[#10B981] font-mono">{uploadQuality.valid_records}</span></span>
                          <span>Invalid: <span className="text-[#E63946] font-mono">{uploadQuality.invalid_records}</span></span>
                          <span>Total: <span className="font-mono">{uploadQuality.total_records}</span></span>
                        </div>
                        {uploadQuality.sample_issues?.length > 0 && (
                          <div className="mt-1 text-[9px] text-[#E63946]">
                            {uploadQuality.sample_issues.slice(0, 3).map((issue, idx) => (
                              <p key={idx}>Row {issue.record}: {issue.issues.join(", ")}</p>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
            <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-chivo text-[#E1E7EF] flex items-center gap-2">
                  <History className="w-4 h-4 text-[#0047FF]" />
                  Upload History
                  {uploads.some((u) => u.is_deleted) && (
                    <Badge className="rounded-sm text-[9px] bg-[#F59E0B]/15 text-[#F59E0B] border-[#F59E0B]/40 ml-auto">
                      Pending deletions
                    </Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {/* Hidden file picker shared by all reupload buttons */}
                <input
                  type="file"
                  ref={reuploadHiddenInputRef}
                  onChange={handleReuploadFile}
                  className="hidden"
                  accept=".csv,.xlsx,.xls,.pdf,.png,.jpg,.jpeg"
                  data-testid="reupload-hidden-input"
                />
                <ScrollArea className="h-80">
                  {uploads.length === 0 ? (
                    <p className="text-xs text-[#6E7681] text-center py-4">No files uploaded yet</p>
                  ) : (
                    <div className="space-y-2 pr-2">
                      {uploads.map((u, i) => (
                        <UploadRow
                          key={u.id}
                          upload={u}
                          index={i}
                          onDelete={() => deleteUpload(u.id, u.file_name)}
                          onUndo={() => undoDeleteUpload(u.id)}
                          onReupload={() => triggerReupload(u.id)}
                          tickKey={tick}
                        />
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ANALYSIS TAB */}
        <TabsContent value="analysis">
          {!analysis ? (
            <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
              <CardContent className="p-12 text-center">
                <Play className="w-8 h-8 text-[#2D333B] mx-auto mb-3" />
                <p className="text-sm text-[#8B949E]">No analysis results yet.</p>
                <p className="text-xs text-[#6E7681] mt-1">Upload data and run analysis from the Overview tab.</p>
                <Button data-testid="run-analysis-cta" onClick={runAnalysis} disabled={analyzing || !caseData.record_count} className="mt-4 bg-[#0047FF] hover:bg-[#003BD6] text-white rounded-sm text-sm">
                  {analyzing ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Analyzing...</> : <><Play className="w-4 h-4 mr-1" /> Run Analysis</>}
                </Button>
              </CardContent>
            </Card>
          ) : (
            <AnalysisReport analysis={analysis} />
          )}
        </TabsContent>

        {/* WHATSAPP TAB */}
        <TabsContent value="whatsapp">
          <WhatsAppTab caseId={caseId} caseData={caseData} />
        </TabsContent>

        {/* REPORT TAB */}
        <TabsContent value="report">
          <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
            <CardHeader>
              <CardTitle className="text-sm font-chivo text-[#E1E7EF] flex items-center gap-2">
                <Download className="w-4 h-4 text-[#0047FF]" /> Download Reports
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!analysis ? (
                <p className="text-xs text-[#6E7681] py-4 text-center">Run analysis first to generate reports.</p>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 border border-[#2D333B] rounded-sm text-center">
                    <FileText className="w-8 h-8 text-[#E63946] mx-auto mb-2" />
                    <p className="text-sm font-medium text-[#E1E7EF]">PDF Report</p>
                    <p className="text-xs text-[#6E7681] mt-1">Professional print-ready format</p>
                    <Button data-testid="download-pdf-btn" onClick={() => downloadReport("pdf")} className="mt-3 bg-[#E63946] hover:bg-[#D92D39] text-white rounded-sm text-xs">
                      <Download className="w-3 h-3 mr-1" /> Download PDF
                    </Button>
                  </div>
                  <div className="p-4 border border-[#2D333B] rounded-sm text-center">
                    <FileText className="w-8 h-8 text-[#0047FF] mx-auto mb-2" />
                    <p className="text-sm font-medium text-[#E1E7EF]">Word Report (.docx)</p>
                    <p className="text-xs text-[#6E7681] mt-1">Editable document format</p>
                    <Button data-testid="download-docx-btn" onClick={() => downloadReport("docx")} className="mt-3 bg-[#0047FF] hover:bg-[#003BD6] text-white rounded-sm text-xs">
                      <Download className="w-3 h-3 mr-1" /> Download DOCX
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * UploadRow — renders one upload entry with:
 *   - Normal mode: filename, metadata, delete + reupload buttons
 *   - Soft-deleted mode: strike-through, countdown timer, Undo button
 */
function UploadRow({ upload, index, onDelete, onUndo, onReupload, tickKey }) {
  const isDeleted = !!upload.is_deleted;
  const reason = upload.deletion_reason;
  // Compute time remaining
  let remainingMs = 0;
  if (isDeleted && upload.deletion_expires_at) {
    remainingMs = new Date(upload.deletion_expires_at).getTime() - Date.now();
    if (remainingMs < 0) remainingMs = 0;
  }
  const expired = isDeleted && remainingMs <= 0;
  const remainSec = Math.ceil(remainingMs / 1000);
  const remainMin = Math.floor(remainSec / 60);
  const remainSecondsPart = remainSec % 60;
  const remainStr = remainSec >= 60 ? `${remainMin}m ${remainSecondsPart}s` : `${remainSec}s`;

  return (
    <div
      data-testid={`upload-row-${index}`}
      className={`p-2 border rounded-sm transition-colors ${
        isDeleted
          ? "bg-[#E63946]/5 border-[#E63946]/30"
          : "bg-[#090A0C] border-[#2D333B]"
      }`}
    >
      <div className="flex items-center gap-2">
        <FileText className={`w-3 h-3 shrink-0 ${isDeleted ? "text-[#E63946]" : "text-[#0047FF]"}`} />
        <span
          className={`text-xs truncate flex-1 ${
            isDeleted ? "text-[#8B949E] line-through" : "text-[#E1E7EF]"
          }`}
        >
          {upload.file_name}
        </span>
        {isDeleted ? (
          <>
            {!expired && (
              <Button
                data-testid={`undo-upload-${index}`}
                variant="ghost"
                size="sm"
                onClick={onUndo}
                className="h-6 px-2 text-[10px] text-[#10B981] hover:text-[#10B981] hover:bg-[#10B981]/10 rounded-sm"
              >
                <RotateCcw className="w-3 h-3 mr-1" />
                Undo
              </Button>
            )}
          </>
        ) : (
          <div className="flex items-center gap-0.5 shrink-0">
            <Button
              data-testid={`reupload-upload-${index}`}
              variant="ghost"
              size="sm"
              onClick={onReupload}
              title="Replace file"
              className="h-5 w-5 p-0 text-[#6E7681] hover:text-[#0047FF]"
            >
              <RefreshCw className="w-3 h-3" />
            </Button>
            <Button
              data-testid={`delete-upload-${index}`}
              variant="ghost"
              size="sm"
              onClick={onDelete}
              title="Delete file"
              className="h-5 w-5 p-0 text-[#6E7681] hover:text-[#E63946]"
            >
              <Trash2 className="w-3 h-3" />
            </Button>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-3 mt-1 text-[10px] text-[#6E7681]">
        <span>{upload.subject_name}</span>
        <span className="uppercase">{upload.file_type}</span>
        <span className="font-mono">{upload.record_count} records</span>
        {upload.quality_score !== undefined && upload.quality_score !== null && !isDeleted && (
          <span
            className={`font-mono ${
              upload.quality_score >= 90
                ? "text-[#10B981]"
                : upload.quality_score >= 70
                ? "text-[#F59E0B]"
                : "text-[#E63946]"
            }`}
          >
            {Math.round(upload.quality_score)}% quality
          </span>
        )}
        {isDeleted && !expired && (
          <span
            data-testid={`countdown-${index}`}
            className="ml-auto font-mono text-[#F59E0B] flex items-center gap-1"
          >
            <AlertTriangle className="w-2.5 h-2.5" />
            {reason === "replaced" ? "Replaced" : "Deleted"} · undo in {remainStr}
          </span>
        )}
        {expired && (
          <span className="ml-auto font-mono text-[#6E7681]">
            Undo window expired (purging…)
          </span>
        )}
      </div>
      {/* Hidden tickKey forces parent re-render; we don't display it */}
      <span className="hidden">{tickKey}</span>
    </div>
  );
}
