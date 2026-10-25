import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  DollarSign, MessageSquare, Clock, File, Lock, MapPin,
  GitBranch, Brain, Users, AlertTriangle, Target, HelpCircle, ChevronDown,
  TrendingUp, Shield, Smartphone, Info, Zap, Activity,
  CreditCard, Radio, Upload, Globe, ArrowUpRight, ArrowDownRight, ShieldAlert,
} from "lucide-react";
import { useState } from "react";
import { Tooltip as UITooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, BarChart, Bar } from "recharts";
import NetworkGraph from "@/components/NetworkGraph";
import LocationMap from "@/components/LocationMap";

// Time-band classifier for temporal overlaps — higher coordination signal = lower seconds
const TIME_BANDS = [
  { max: 60, label: "CRITICAL", color: "#E63946", bg: "#E6394620", desc: "<1 min — strong coordination signal" },
  { max: 300, label: "HIGH", color: "#F59E0B", bg: "#F59E0B20", desc: "1–5 min — likely coordinated" },
  { max: 1800, label: "MEDIUM", color: "#FBBF24", bg: "#FBBF2420", desc: "5–30 min — possible coordination" },
  { max: 3600, label: "LOW", color: "#10B981", bg: "#10B98120", desc: "30–60 min — weak signal" },
];

const classifyTimeDiff = (sec) => TIME_BANDS.find((b) => sec <= b.max) || TIME_BANDS[TIME_BANDS.length - 1];

const formatDiff = (sec) => {
  if (sec < 60) return `${Math.round(sec)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
  return `${(sec / 3600).toFixed(1)}h`;
};

function InfoTip({ children }) {
  return (
    <TooltipProvider delayDuration={150}>
      <UITooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            data-testid="info-tooltip-trigger"
            className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-[#1C1F26] border border-[#2D333B] hover:border-[#0047FF] hover:bg-[#0047FF]/10 transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <Info className="w-2.5 h-2.5 text-[#6E7681]" />
          </button>
        </TooltipTrigger>
        <TooltipContent
          side="right"
          className="max-w-xs bg-[#0D0F14] border border-[#2D333B] text-[#E1E7EF] text-[11px] leading-relaxed p-3 rounded-sm"
        >
          {children}
        </TooltipContent>
      </UITooltip>
    </TooltipProvider>
  );
}

const riskColor = (level) => {
  const m = { CRITICAL: "#E63946", HIGH: "#E63946", MEDIUM: "#F59E0B", LOW: "#10B981" };
  return m[level] || "#8B949E";
};

const catColor = (cat) => {
  const m = { crypto: "#F59E0B", messaging: "#0047FF", file_transfer: "#10B981", social: "#A78BFA", vpn_proxy: "#E63946", email: "#8B949E" };
  return m[cat] || "#6E7681";
};

function Section({ icon: Icon, title, color, children, defaultOpen = false, subtitle, tooltip }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
        <CollapsibleTrigger className="w-full" asChild>
          <CardHeader className="pb-2 cursor-pointer hover:bg-[#1C1F26] transition-colors rounded-t-sm">
            <CardTitle className="text-xs font-chivo text-[#E1E7EF] flex items-center gap-2">
              <Icon className="w-4 h-4" style={{ color }} />
              <span className="flex-1 text-left">{title}</span>
              {tooltip && <InfoTip>{tooltip}</InfoTip>}
              <ChevronDown className={`w-3 h-3 text-[#6E7681] transition-transform ${open ? "rotate-180" : ""}`} />
            </CardTitle>
            {subtitle && (
              <p className="text-[10px] text-[#6E7681] font-normal mt-1 text-left leading-relaxed">{subtitle}</p>
            )}
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="pt-0 pb-3">{children}</CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}

function DataRow({ label, value, mono = false }) {
  return (
    <div className="flex justify-between py-1 text-xs border-b border-[#2D333B]/50 last:border-0">
      <span className="text-[#6E7681]">{label}</span>
      <span className={`text-[#E1E7EF] ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}

export default function AnalysisReport({ analysis }) {
  if (!analysis) return null;

  return (
    <div data-testid="analysis-report" className="space-y-3">
      {/* Summary */}
      <Card className="bg-[#13151A] border-[#0047FF]/30 rounded-sm pulse-glow">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <Shield className="w-4 h-4 text-[#0047FF]" />
            <span className="text-xs font-chivo font-bold text-[#E1E7EF] uppercase tracking-[0.15em]">Executive Summary</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-3">
            {[
              { l: "Subjects", v: analysis.summary?.total_subjects },
              { l: "High Risk", v: analysis.summary?.high_risk_subjects?.length, c: "#E63946" },
              { l: "Crypto Events", v: analysis.summary?.total_crypto_hits, c: "#F59E0B" },
              { l: "Temporal Overlaps", v: analysis.summary?.total_temporal_overlaps, c: "#0047FF" },
              { l: "Common Contacts", v: analysis.summary?.total_common_contacts, c: "#10B981" },
            ].map((s) => (
              <div key={s.l} className="text-center">
                <p className="text-[10px] uppercase tracking-[0.15em] text-[#6E7681]">{s.l}</p>
                <p className="text-lg font-bold font-mono" style={{ color: s.c || "#E1E7EF" }}>{s.v || 0}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Risk Scores */}
      <Card className="bg-[#13151A] border-[#2D333B] rounded-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-chivo text-[#E1E7EF] flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-[#E63946]" /> Risk Assessment
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {Object.entries(analysis.risk_scores || {}).map(([subject, data]) => (
              <div key={subject} data-testid={`risk-score-${subject}`} className="p-3 bg-[#090A0C] border border-[#2D333B] rounded-sm">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-[#E1E7EF]">{subject}</span>
                  <Badge className="rounded-sm text-[10px]" style={{ background: `${riskColor(data.level)}20`, color: riskColor(data.level), borderColor: `${riskColor(data.level)}50` }}>
                    {data.level}
                  </Badge>
                </div>
                <div className="flex items-center gap-2 mb-2">
                  <div className="flex-1 h-1.5 bg-[#2D333B] rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all" style={{ width: `${data.score}%`, background: riskColor(data.level) }} />
                  </div>
                  <span className="text-xs font-mono" style={{ color: riskColor(data.level) }}>{data.score}/100</span>
                </div>
                {data.factors?.map((f, i) => (
                  <p key={i} className="text-[10px] text-[#8B949E] mt-0.5">{f}</p>
                ))}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Sections */}
      <Section icon={DollarSign} title="1. Funding Correlation" color="#F59E0B" defaultOpen>
        <FundingSection data={analysis.funding_correlation} />
      </Section>

      <Section icon={MessageSquare} title="2. Communication Probability Analysis" color="#0047FF" defaultOpen>
        <CommProbSection data={analysis.communication_probability} />
      </Section>

      <Section
        icon={Clock}
        title="3. Temporal Overlap"
        color="#A78BFA"
        subtitle="Events from different subjects occurring close in time — strong indicator of coordination, shared events, or relayed activity."
        tooltip={
          <div className="space-y-2">
            <p className="font-bold text-[#A78BFA]">What is Temporal Overlap?</p>
            <p>
              When two subjects perform activity (calls, app usage, data sessions) within a short window of
              each other, it suggests they may be <span className="text-[#E1E7EF] font-semibold">coordinating</span>,
              attending the same event, or relaying messages.
            </p>
            <p className="font-bold text-[#A78BFA] pt-1">How to read it:</p>
            <ul className="space-y-1 text-[10px]">
              <li><span className="text-[#E63946] font-bold">CRITICAL (&lt;1 min)</span> — strong coordination signal</li>
              <li><span className="text-[#F59E0B] font-bold">HIGH (1–5 min)</span> — likely coordinated</li>
              <li><span className="text-[#FBBF24] font-bold">MEDIUM (5–30 min)</span> — possible coordination</li>
              <li><span className="text-[#10B981] font-bold">LOW (30–60 min)</span> — weak coincidence signal</li>
            </ul>
            <p className="text-[10px] text-[#8B949E] pt-1">
              Investigative use: pair with location overlaps, common platforms, or shared contacts to
              corroborate the link.
            </p>
          </div>
        }
      >
        <TemporalSection data={analysis.temporal_overlap} />
      </Section>

      <Section icon={File} title="4. File Transfer Indicators" color="#10B981">
        <FileTransferSection data={analysis.file_transfer} />
      </Section>

      <Section icon={Lock} title="5. Secure Messaging Usage" color="#E63946">
        <SecureMessagingSection data={analysis.secure_messaging} />
      </Section>

      <Section icon={MapPin} title="6. Location of Suspects" color="#F59E0B">
        <LocationSection data={analysis.location_correlation} />
      </Section>

      <Section icon={GitBranch} title="7. Communication Likelihood Matrix" color="#0047FF">
        <LikelihoodSection data={analysis.communication_likelihood} />
      </Section>

      <Section
        icon={GitBranch}
        title="8. Relationship Graph"
        color="#A78BFA"
        defaultOpen
        subtitle="Network of subjects, the platforms they use, and their shared contacts. Hover any node to highlight its connections."
        tooltip={
          <div className="space-y-2">
            <p className="font-bold text-[#A78BFA]">How to read the graph</p>
            <ul className="space-y-1 text-[10px]">
              <li>
                <span className="inline-block w-2 h-2 rounded-full bg-[#0047FF] mr-1 align-middle" />
                <span className="text-[#E1E7EF] font-semibold">Inner ring</span>: subjects (size = degree of connections)
              </li>
              <li>
                <span className="inline-block w-2 h-2 rounded-full bg-[#F59E0B] mr-1 align-middle" />
                <span className="text-[#E1E7EF] font-semibold">Middle ring</span>: platforms grouped by category color
              </li>
              <li>
                <span className="inline-block w-2 h-2 rounded-full bg-[#8B949E] mr-1 align-middle" />
                <span className="text-[#E1E7EF] font-semibold">Outer ring</span>: shared contacts between subjects
              </li>
            </ul>
            <p className="text-[10px] text-[#8B949E] pt-1">
              Multi-link contacts (touching multiple subjects) are the strongest leads — investigate their identities first.
            </p>
          </div>
        }
      >
        <NetworkGraph data={analysis.relationship_graph} />
      </Section>

      <Section icon={Brain} title="9. Behavioral Profiling" color="#10B981">
        <BehavioralSection data={analysis.behavioral_profiling} />
      </Section>

      <Section icon={Users} title="10. Common Contacts Analysis" color="#0047FF">
        <CommonContactsSection data={analysis.common_contacts} />
      </Section>

      <Section icon={Smartphone} title="11. IMEI Analysis" color="#F59E0B">
        <ImeiSection data={analysis.imei_analysis} />
      </Section>

      <Section
        icon={CreditCard}
        title="12. SIM / IMSI Analysis"
        color="#06B6D4"
        subtitle="SIM identity tracking — detects foreign SIMs, SIM-swapping behaviour, and IMSIs shared across subjects."
        tooltip={
          <div className="space-y-2">
            <p className="font-bold text-[#06B6D4]">What is IMSI?</p>
            <p>
              IMSI (International Mobile Subscriber Identity) is the unique 14–15 digit identifier
              of a SIM card. The first 3 digits (MCC) identify the country of issue.
            </p>
            <p className="font-bold text-[#06B6D4] pt-1">Three signals to watch:</p>
            <ul className="space-y-1 text-[10px]">
              <li><span className="text-[#E63946] font-bold">Foreign SIM</span> — MCC outside India (404/405/406). Pakistan = 410, China = 460, USA = 310.</li>
              <li><span className="text-[#F59E0B] font-bold">Multi-SIM / SIM-Swap</span> — same device (IMEI) used with multiple IMSIs = burner-SIM behaviour.</li>
              <li><span className="text-[#A78BFA] font-bold">Shared IMSI</span> — same SIM appears in records of multiple subjects = passed-around / relay SIM.</li>
            </ul>
          </div>
        }
      >
        <SimAnalysisSection data={analysis.sim_analysis} />
      </Section>

      <Section
        icon={Radio}
        title="13. Cell Tower Co-Location"
        color="#A78BFA"
        subtitle="Subjects appearing on the same cell tower within ±5 minutes — strong evidence of physical co-presence."
        tooltip={
          <div className="space-y-2">
            <p className="font-bold text-[#A78BFA]">What is Cell Co-Location?</p>
            <p>
              When two suspects' phones register on the same cell tower within a few minutes of each other,
              they are almost certainly within the tower's footprint at the same time
              (typically <span className="text-[#E1E7EF] font-semibold">300m–1km</span>).
            </p>
            <p className="font-bold text-[#A78BFA] pt-1">Why it matters:</p>
            <ul className="space-y-1 text-[10px]">
              <li>Stronger than city-level geocoding (sub-km vs city-wide)</li>
              <li>Proves physical proximity even when no call was made</li>
              <li>Reveals meeting locations and travel-route hand-offs</li>
            </ul>
            <p className="text-[10px] text-[#8B949E] pt-1">
              <span className="text-[#E63946] font-bold">High-priority pairs</span> are those appearing
              together at multiple distinct cell towers — that's a relationship, not a coincidence.
            </p>
          </div>
        }
      >
        <CellColocationSection data={analysis.cell_colocation} />
      </Section>

      <Section
        icon={Upload}
        title="14. Bulk Data Transfer Alerts"
        color="#E63946"
        subtitle="Large IPDR sessions (>10 MB) flagged by severity. Upload-heavy traffic is a classic data-exfiltration signature."
        tooltip={
          <div className="space-y-2">
            <p className="font-bold text-[#E63946]">What is flagged?</p>
            <p>
              IPDR sessions where uploaded + downloaded volume exceeds normal browsing bandwidth.
              Useful for spotting <span className="text-[#E1E7EF] font-semibold">document leaks</span>,
              cloud-backup of stolen data, or large media exchange.
            </p>
            <p className="font-bold text-[#E63946] pt-1">Severity bands:</p>
            <ul className="space-y-1 text-[10px]">
              <li><span className="text-[#E63946] font-bold">ALERT</span> — single session &gt; 500 MB</li>
              <li><span className="text-[#F59E0B] font-bold">HIGH</span> — 50 MB – 500 MB</li>
              <li><span className="text-[#FBBF24] font-bold">MEDIUM</span> — 10 MB – 50 MB</li>
            </ul>
            <p className="text-[10px] text-[#8B949E] pt-1">
              <span className="text-[#E63946] font-bold">Upload-heavy</span> (upload ≥ 3× download)
              is a strong exfiltration signature — investigate destination and timing first.
            </p>
          </div>
        }
      >
        <BulkTransferSection data={analysis.bulk_transfer_analysis} />
      </Section>

      <Section icon={Target} title="15. Priority Leads" color="#E63946">
        <PriorityLeadsSection data={analysis.priority_leads} />
      </Section>

      <Section icon={HelpCircle} title="16. Interrogation Questions" color="#F59E0B">
        <QuestionsSection data={analysis.interrogation_questions} />
      </Section>
    </div>
  );
}

function FundingSection({ data }) {
  if (!data) return <p className="text-xs text-[#6E7681]">No data</p>;
  return (
    <div className="space-y-2">
      <p className="text-xs text-[#8B949E]">Total crypto hits: <span className="font-mono text-[#F59E0B]">{data.total_crypto_hits}</span></p>
      {Object.entries(data.subject_activity || {}).map(([subject, hits]) => (
        <div key={subject}>
          <p className="text-xs font-medium text-[#E1E7EF] mb-1">{subject}</p>
          <div className="space-y-0.5">
            {hits.slice(0, 5).map((h, i) => (
              <div key={i} className="flex gap-4 text-[10px] text-[#8B949E]">
                <span className="text-[#F59E0B] font-mono">{h.platform}</span>
                <span className="font-mono">{h.ip || "N/A"}</span>
                <span className="font-mono">{h.timestamp || "N/A"}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
      {data.correlations?.map((c, i) => (
        <div key={i} className="p-2 bg-[#F59E0B]/10 border border-[#F59E0B]/20 rounded-sm">
          <Badge className="rounded-sm text-[10px] mb-1" style={{ background: c.strength === "HIGH" ? "#E6394620" : "#F59E0B20", color: c.strength === "HIGH" ? "#E63946" : "#F59E0B" }}>
            {c.strength}
          </Badge>
          <p className="text-xs text-[#E1E7EF]">{c.inference}</p>
        </div>
      ))}
      {data.total_crypto_hits === 0 && <p className="text-xs text-[#6E7681]">No cryptocurrency platform activity detected</p>}
    </div>
  );
}

function CommProbSection({ data }) {
  if (!data) return null;
  const allPlats = data.all_platforms || [];
  const matrix = data.platform_matrix || {};
  if (allPlats.length === 0) return <p className="text-xs text-[#6E7681]">No communication platforms detected</p>;
  return (
    <ScrollArea className="w-full">
      <table className="w-full table-dense">
        <thead>
          <tr className="border-b border-[#2D333B]">
            <th className="text-left p-1.5">Subject</th>
            {allPlats.map((p) => <th key={p} className="text-center p-1.5 whitespace-nowrap">{p}</th>)}
          </tr>
        </thead>
        <tbody>
          {Object.entries(matrix).map(([subject, plats]) => (
            <tr key={subject} className="border-b border-[#2D333B]/50">
              <td className="p-1.5 text-[#E1E7EF]">{subject}</td>
              {allPlats.map((p) => (
                <td key={p} className="p-1.5 text-center">
                  {plats[p] ? <span className="text-[#10B981] font-bold">Y</span> : <span className="text-[#2D333B]">-</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollArea>
  );
}

function TemporalSection({ data }) {
  if (!data) return null;
  const events = data.overlapping_events || [];
  const total = data.total_overlaps || 0;

  // Distribution by time-band (for histogram + summary cards)
  const bandCounts = TIME_BANDS.map((b) => ({ ...b, count: 0 }));
  events.forEach((e) => {
    const idx = TIME_BANDS.findIndex((b) => e.time_diff_seconds <= b.max);
    if (idx >= 0) bandCounts[idx].count += 1;
  });

  // Per-pair aggregation for top-coordinated pairs
  const pairAgg = {};
  events.forEach((e) => {
    const key = [e.event1.subject, e.event2.subject].sort().join(" ⇄ ");
    if (!pairAgg[key]) pairAgg[key] = { count: 0, minDiff: Infinity, samples: [] };
    pairAgg[key].count += 1;
    if (e.time_diff_seconds < pairAgg[key].minDiff) pairAgg[key].minDiff = e.time_diff_seconds;
    if (pairAgg[key].samples.length < 1) pairAgg[key].samples.push(e);
  });
  const topPairs = Object.entries(pairAgg)
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 4);

  if (events.length === 0) {
    return (
      <div className="text-center py-6 text-[#6E7681]">
        <Activity className="w-8 h-8 mx-auto mb-2 opacity-30" />
        <p className="text-xs">No temporal overlaps detected within the 60-minute correlation window</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Time-band summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {bandCounts.map((b) => (
          <div
            key={b.label}
            className="rounded-sm p-2 border"
            style={{
              borderColor: `${b.color}40`,
              background: `linear-gradient(135deg, ${b.bg}, transparent)`,
            }}
            data-testid={`temporal-band-${b.label.toLowerCase()}`}
          >
            <div className="flex items-center justify-between">
              <span className="text-[9px] font-chivo font-bold uppercase tracking-wider" style={{ color: b.color }}>
                {b.label}
              </span>
              <Zap className="w-3 h-3" style={{ color: b.color, opacity: b.count > 0 ? 1 : 0.25 }} />
            </div>
            <div className="text-xl font-chivo font-bold mt-1" style={{ color: b.color }}>
              {b.count}
            </div>
            <div className="text-[9px] text-[#6E7681] leading-tight">{b.desc}</div>
          </div>
        ))}
      </div>

      {/* Top coordinated pairs */}
      {topPairs.length > 0 && (
        <div className="bg-[#090A0C] border border-[#2D333B] rounded-sm p-2">
          <div className="flex items-center gap-1.5 mb-2">
            <TrendingUp className="w-3 h-3 text-[#A78BFA]" />
            <span className="text-[10px] font-chivo font-bold text-[#E1E7EF] uppercase tracking-wider">
              Most Frequently Overlapping Pairs
            </span>
          </div>
          <div className="space-y-1">
            {topPairs.map(([pair, info]) => {
              const band = classifyTimeDiff(info.minDiff);
              return (
                <div
                  key={pair}
                  className="flex items-center gap-2 text-[10px] p-1.5 rounded-sm hover:bg-[#13151A] transition-colors"
                  data-testid="temporal-pair-row"
                >
                  <div
                    className="w-1 h-6 rounded-full flex-shrink-0"
                    style={{ background: band.color }}
                  />
                  <span className="text-[#E1E7EF] font-mono flex-1 truncate">{pair}</span>
                  <span className="text-[#6E7681]">
                    closest: <span className="font-mono" style={{ color: band.color }}>{formatDiff(info.minDiff)}</span>
                  </span>
                  <span className="px-1.5 py-0.5 bg-[#13151A] border border-[#2D333B] rounded-sm font-mono text-[#A78BFA]">
                    {info.count}×
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Header + total */}
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-[#6E7681] uppercase tracking-wider font-chivo">
          Top Overlapping Events
        </span>
        <span className="text-[10px] text-[#8B949E]">
          Total: <span className="font-mono text-[#A78BFA] font-bold">{total}</span>
          {events.length < total && (
            <span className="text-[#6E7681]"> · showing {events.length}</span>
          )}
        </span>
      </div>

      {/* Event timeline cards */}
      <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
        {events.slice(0, 20).map((e, i) => {
          const band = classifyTimeDiff(e.time_diff_seconds);
          return (
            <div
              key={i}
              className="rounded-sm border bg-[#0D0F14] hover:bg-[#13151A] transition-colors overflow-hidden"
              style={{ borderColor: `${band.color}30` }}
              data-testid="temporal-event-card"
            >
              <div className="flex items-stretch">
                <div
                  className="w-1 flex-shrink-0"
                  style={{ background: band.color }}
                />
                <div className="flex-1 p-2">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge
                      className="rounded-sm text-[9px] font-bold px-1.5 py-0 h-4"
                      style={{ background: band.bg, color: band.color, borderColor: `${band.color}40` }}
                    >
                      {band.label}
                    </Badge>
                    <span className="text-[10px] font-mono font-bold" style={{ color: band.color }}>
                      {formatDiff(e.time_diff_seconds)} apart
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px]">
                    <div className="flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#0047FF]" />
                      <span className="text-[#E1E7EF] font-medium">{e.event1.subject}</span>
                      <span className="text-[#6E7681] font-mono">({e.event1.platform || "—"})</span>
                      <span className="text-[#6E7681] font-mono text-[9px]">{e.event1.timestamp?.replace("T", " ").slice(0, 19)}</span>
                    </div>
                    <span className="text-[#2D333B]">↔</span>
                    <div className="flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                      <span className="text-[#E1E7EF] font-medium">{e.event2.subject}</span>
                      <span className="text-[#6E7681] font-mono">({e.event2.platform || "—"})</span>
                      <span className="text-[#6E7681] font-mono text-[9px]">{e.event2.timestamp?.replace("T", " ").slice(0, 19)}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FileTransferSection({ data }) {
  if (!data) return null;
  const activity = data.subject_activity || {};
  return (
    <div className="space-y-2">
      {Object.entries(activity).map(([subject, hits]) => {
        const plats = [...new Set(hits.map((h) => h.platform))];
        return (
          <div key={subject} className="text-xs">
            <span className="text-[#E1E7EF]">{subject}: </span>
            {plats.map((p) => (
              <Badge key={p} className="rounded-sm text-[10px] mr-1 bg-[#10B981]/15 text-[#10B981] border-[#10B981]/30">{p}</Badge>
            ))}
          </div>
        );
      })}
      {data.shared_usage?.map((s, i) => (
        <p key={i} className="text-xs text-[#10B981] bg-[#10B981]/10 p-2 rounded-sm border border-[#10B981]/20">{s.inference}</p>
      ))}
      {Object.keys(activity).length === 0 && <p className="text-xs text-[#6E7681]">No file transfer activity detected</p>}
    </div>
  );
}

function SecureMessagingSection({ data }) {
  if (!data) return null;
  const findings = data.encryption_findings || {};
  return (
    <div className="space-y-2">
      {Object.entries(findings).map(([subject, f]) => (
        <div key={subject} className="p-2 bg-[#E63946]/10 border border-[#E63946]/20 rounded-sm">
          <span className="text-xs font-medium text-[#E1E7EF]">{subject}: </span>
          {f.platforms?.map((p) => (
            <Badge key={p} className="rounded-sm text-[10px] mr-1 bg-[#E63946]/15 text-[#E63946] border-[#E63946]/30">{p}</Badge>
          ))}
          <p className="text-[10px] text-[#8B949E] mt-1">{f.risk_note} ({f.session_count} sessions)</p>
        </div>
      ))}
      {Object.keys(findings).length === 0 && <p className="text-xs text-[#6E7681]">No encrypted messaging detected</p>}
    </div>
  );
}

function LocationSection({ data }) {
  if (!data) return null;
  return (
    <div className="space-y-3">
      {/* Interactive Map */}
      <LocationMap data={data} />

      {/* Subject locations list */}
      <div className="space-y-1">
        {Object.entries(data.subject_locations || {}).map(([subject, loc]) => (
          <DataRow key={subject} label={subject} value={loc} mono />
        ))}
      </div>

      {/* Pairwise comparisons */}
      {data.comparisons?.map((c, i) => (
        <div key={i} className="flex items-center gap-2 p-2 bg-[#090A0C] border border-[#2D333B] rounded-sm">
          <span className="text-xs text-[#E1E7EF]">{c.subjects.join(" / ")}</span>
          <span className="text-[10px] text-[#8B949E] flex-1">{c.note}</span>
          {c.distance_km != null && (
            <span className="text-xs font-mono font-bold text-[#F59E0B]">{c.distance_km} km</span>
          )}
        </div>
      ))}

      {Object.keys(data.subject_locations || {}).length === 0 && (
        <p className="text-xs text-[#6E7681]">No location data available. Add location info to subjects for geospatial analysis.</p>
      )}
    </div>
  );
}

function LikelihoodSection({ data }) {
  if (!data) return null;
  return (
    <div className="space-y-2">
      {data.pairs?.map((p, i) => (
        <div key={i} className="flex items-center gap-3 p-2 bg-[#090A0C] border border-[#2D333B] rounded-sm">
          <span className="text-xs text-[#E1E7EF] flex-1">{p.subject1} &lt;-&gt; {p.subject2}</span>
          <Badge className="rounded-sm text-[10px]" style={{ background: `${riskColor(p.likelihood)}20`, color: riskColor(p.likelihood) }}>
            {p.likelihood}
          </Badge>
          <span className="text-[10px] font-mono text-[#6E7681]">{(p.overlap_ratio * 100).toFixed(0)}%</span>
        </div>
      ))}
      {(!data.pairs || data.pairs.length === 0) && <p className="text-xs text-[#6E7681]">Insufficient data for likelihood analysis</p>}
    </div>
  );
}

function BehavioralSection({ data }) {
  if (!data) return null;
  return (
    <div className="space-y-2">
      {Object.entries(data.profiles || {}).map(([subject, p]) => (
        <div key={subject} className="p-3 bg-[#090A0C] border border-[#2D333B] rounded-sm">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-[#E1E7EF]">{subject}</span>
            <Badge className="rounded-sm text-[10px] bg-[#0047FF]/15 text-[#0047FF] border-[#0047FF]/30">{p.role}</Badge>
          </div>
          <div className="flex flex-wrap gap-1 mb-1">
            {p.behavior_type?.map((b) => (
              <span key={b} className="text-[10px] px-1.5 py-0.5 bg-[#1C1F26] text-[#8B949E] rounded-sm">{b}</span>
            ))}
          </div>
          <p className="text-[10px] text-[#6E7681]">Platforms: {p.platforms_used?.join(", ") || "None"}</p>
          {p.imeis?.length > 0 && <p className="text-[10px] font-mono text-[#6E7681]">IMEI: {p.imeis.join(", ")}</p>}
          {p.risk_indicators?.map((r, i) => (
            <p key={i} className="text-[10px] text-[#F59E0B] mt-0.5">! {r}</p>
          ))}
        </div>
      ))}
      {data.shared_devices && Object.keys(data.shared_devices).length > 0 && (
        <div className="p-2 bg-[#E63946]/10 border border-[#E63946]/20 rounded-sm">
          <p className="text-xs font-medium text-[#E63946] mb-1">Shared Devices Detected</p>
          {Object.entries(data.shared_devices).map(([imei, subjects]) => (
            <p key={imei} className="text-[10px] font-mono text-[#8B949E]">IMEI {imei}: {subjects.join(", ")}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function CommonContactsSection({ data }) {
  if (!data) return null;
  return (
    <div className="space-y-2">
      <p className="text-xs text-[#8B949E]">Total shared contacts: <span className="font-mono text-[#0047FF]">{data.total_common_contacts}</span></p>
      {Object.entries(data.pairwise_common || {}).map(([pair, d]) => (
        <div key={pair} className="p-2 bg-[#090A0C] border border-[#2D333B] rounded-sm space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-[#E1E7EF]">{pair}</span>
            <span className="font-mono text-[#0047FF]">{d.count} common</span>
          </div>
          {d.details?.slice(0, 8).map((detail, i) => (
            <div key={i} className="mt-1 p-1.5 bg-[#13151A] rounded-sm border border-[#2D333B]/50">
              <div className="flex items-center gap-3 text-[10px]">
                <span className="font-mono text-[#E1E7EF]">{detail.number}</span>
                {Object.entries(detail).filter(([k]) => k.endsWith("_calls")).map(([k, v]) => (
                  <span key={k} className="text-[#6E7681]">{k.replace("_calls", "")}: <span className="text-[#F59E0B] font-mono">{v}</span> calls</span>
                ))}
              </div>
              {Object.entries(detail).filter(([k]) => k.endsWith("_sample_times")).map(([k, times]) => (
                times && times.length > 0 && (
                  <div key={k} className="mt-0.5">
                    <span className="text-[9px] text-[#6E7681] uppercase">{k.replace("_sample_times", "")}:</span>
                    {times.slice(0, 3).map((t, j) => (
                      <span key={j} className="text-[9px] font-mono text-[#8B949E] ml-1">{t.date} {t.time} ({t.type})</span>
                    ))}
                  </div>
                )
              ))}
            </div>
          ))}
          {(!d.details || d.details.length === 0) && d.numbers?.length > 0 && (
            <p className="text-[10px] font-mono text-[#6E7681] mt-1 truncate">{d.numbers.slice(0, 5).join(", ")}</p>
          )}
        </div>
      ))}
      {data.common_across_all?.length > 0 && (
        <div className="p-2 bg-[#E63946]/10 border border-[#E63946]/20 rounded-sm">
          <p className="text-xs font-medium text-[#E63946] mb-1">Common Across ALL Subjects</p>
          {data.common_across_all.map((num) => (
            <p key={num} className="text-[10px] font-mono text-[#8B949E]">{num}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function ImeiSection({ data }) {
  if (!data) return null;
  return (
    <div className="space-y-2">
      <p className="text-xs text-[#8B949E]">Total unique IMEIs: <span className="font-mono text-[#F59E0B]">{data.total_unique_imeis || 0}</span></p>
      {/* Per-subject IMEIs */}
      {Object.entries(data.subject_imeis || {}).map(([subject, imeis]) => (
        <div key={subject} className="p-2 bg-[#090A0C] border border-[#2D333B] rounded-sm">
          <p className="text-xs font-medium text-[#E1E7EF] mb-1">{subject}</p>
          {Object.entries(imeis).map(([imei, info]) => (
            <div key={imei} className="flex items-center gap-3 text-[10px] mt-0.5">
              <span className="font-mono text-[#F59E0B]">{imei}</span>
              <span className="text-[#6E7681]">{info.call_count} records</span>
              {info.first_seen && <span className="text-[#8B949E] font-mono">{info.first_seen?.slice(0, 10)} to {info.last_seen?.slice(0, 10)}</span>}
            </div>
          ))}
          {Object.keys(imeis).length === 0 && <p className="text-[10px] text-[#6E7681]">No IMEI data in records</p>}
        </div>
      ))}
      {/* Shared IMEIs - HIGH PRIORITY */}
      {data.shared_imeis?.length > 0 && (
        <div className="p-2 bg-[#E63946]/10 border border-[#E63946]/20 rounded-sm">
          <p className="text-xs font-medium text-[#E63946] mb-1">Shared IMEIs Detected (Device Sharing/Swapping)</p>
          {data.shared_imeis.map((finding, i) => (
            <div key={i} className="mt-1 p-1.5 bg-[#090A0C] rounded-sm">
              <div className="flex items-center gap-2">
                <Badge className="rounded-sm text-[10px] bg-[#E63946]/20 text-[#E63946] border-[#E63946]/30">{finding.risk}</Badge>
                <span className="text-[10px] font-mono text-[#E1E7EF]">{finding.imei}</span>
              </div>
              <p className="text-[10px] text-[#8B949E] mt-0.5">{finding.note}</p>
              {finding.users?.map((u, j) => (
                <div key={j} className="flex gap-3 text-[9px] text-[#6E7681] mt-0.5">
                  <span className="text-[#E1E7EF]">{u.subject}</span>
                  <span className="font-mono">{u.call_count} records</span>
                  <span className="font-mono">{u.first_seen?.slice(0, 10)} to {u.last_seen?.slice(0, 10)}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
      {(!data.shared_imeis || data.shared_imeis.length === 0) && (
        <p className="text-xs text-[#6E7681]">No shared IMEIs detected across subjects</p>
      )}
    </div>
  );
}

function SimAnalysisSection({ data }) {
  if (!data) return null;
  if (!data.has_imsi_data) {
    return (
      <div className="text-center py-6 text-[#6E7681]">
        <CreditCard className="w-8 h-8 mx-auto mb-2 opacity-30" />
        <p className="text-xs">No IMSI metadata available in uploaded records</p>
        <p className="text-[10px] mt-1">SIM analysis requires CDR/IPDR datasets that include the IMSI field.</p>
      </div>
    );
  }

  const foreignSims = data.foreign_sims || [];
  const multiImsi = data.multi_imsi_subjects || [];
  const sharedImsis = data.shared_imsis || [];
  const simSwaps = data.sim_swaps || [];
  const perSubject = data.per_subject || {};

  return (
    <div className="space-y-3">
      {/* Top alert cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <AlertCard
          label="Foreign SIM"
          count={foreignSims.length}
          color="#E63946"
          icon={Globe}
          desc="non-Indian MCC"
          testId="alert-foreign-sim"
        />
        <AlertCard
          label="SIM-Swap"
          count={simSwaps.length}
          color="#F59E0B"
          icon={CreditCard}
          desc="multi-IMSI on one IMEI"
          testId="alert-sim-swap"
        />
        <AlertCard
          label="Multi-SIM Subjects"
          count={multiImsi.length}
          color="#A78BFA"
          icon={Smartphone}
          desc=">1 IMSI per subject"
          testId="alert-multi-imsi"
        />
        <AlertCard
          label="Shared IMSI"
          count={sharedImsis.length}
          color="#06B6D4"
          icon={Users}
          desc="cross-subject reuse"
          testId="alert-shared-imsi"
        />
      </div>

      {/* Foreign SIM events */}
      {foreignSims.length > 0 && (
        <div className="bg-[#E6394610] border border-[#E63946]/30 rounded-sm p-2">
          <div className="flex items-center gap-1.5 mb-2">
            <ShieldAlert className="w-3 h-3 text-[#E63946]" />
            <span className="text-[10px] font-chivo font-bold text-[#E63946] uppercase tracking-wider">
              Foreign-SIM Detections
            </span>
          </div>
          <div className="space-y-1">
            {foreignSims.map((f, i) => (
              <div key={i} className="flex items-center gap-2 text-[10px] p-1.5 bg-[#0D0F14] rounded-sm" data-testid="foreign-sim-row">
                <Badge className="rounded-sm text-[9px] bg-[#E6394620] text-[#E63946] border-[#E63946]/40">
                  {f.country?.toUpperCase()}
                </Badge>
                <span className="text-[#E1E7EF] font-medium">{f.subject}</span>
                <span className="text-[#6E7681]">·</span>
                <span className="font-mono text-[#06B6D4]">{f.imsi}</span>
                <span className="text-[#6E7681]">MCC {f.mcc}</span>
                <span className="text-[#F59E0B] font-mono ml-auto">{f.count}× sessions</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SIM-swap events */}
      {simSwaps.length > 0 && (
        <div className="bg-[#F59E0B10] border border-[#F59E0B]/30 rounded-sm p-2">
          <div className="flex items-center gap-1.5 mb-2">
            <ShieldAlert className="w-3 h-3 text-[#F59E0B]" />
            <span className="text-[10px] font-chivo font-bold text-[#F59E0B] uppercase tracking-wider">
              SIM-Swap Patterns (one IMEI, multiple IMSIs)
            </span>
          </div>
          <div className="space-y-1">
            {simSwaps.map((s, i) => (
              <div key={i} className="p-1.5 bg-[#0D0F14] rounded-sm" data-testid="sim-swap-row">
                <div className="flex items-center gap-2 text-[10px] mb-1">
                  <span className="text-[#6E7681]">IMEI:</span>
                  <span className="font-mono text-[#F59E0B]">{s.imei}</span>
                  <Badge className="rounded-sm text-[9px] bg-[#F59E0B20] text-[#F59E0B] ml-auto">
                    {s.imsis.length} SIMs
                  </Badge>
                </div>
                <div className="flex flex-wrap gap-1 mt-1">
                  {s.imsis.map((imsi, j) => (
                    <span key={j} className="font-mono text-[9px] text-[#06B6D4] bg-[#0D0F14] border border-[#2D333B] px-1.5 py-0.5 rounded-sm">
                      {imsi}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per-subject IMSI roster */}
      <div className="bg-[#090A0C] border border-[#2D333B] rounded-sm p-2">
        <div className="flex items-center gap-1.5 mb-2">
          <CreditCard className="w-3 h-3 text-[#06B6D4]" />
          <span className="text-[10px] font-chivo font-bold text-[#E1E7EF] uppercase tracking-wider">
            Per-Subject SIM Roster
          </span>
        </div>
        {Object.entries(perSubject).map(([subject, info]) => (
          <div key={subject} className="border-b border-[#2D333B] last:border-0 py-1.5">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[#E1E7EF] text-xs font-medium">{subject}</span>
              <span className="text-[10px] text-[#6E7681]">·</span>
              <span className="text-[10px] text-[#06B6D4] font-mono">{info.imsi_count} IMSI</span>
              {info.foreign_count > 0 && (
                <Badge className="rounded-sm text-[9px] bg-[#E6394620] text-[#E63946] border-[#E63946]/30">
                  {info.foreign_count} FOREIGN
                </Badge>
              )}
            </div>
            {info.imsis?.length > 0 ? (
              <div className="space-y-0.5 ml-2">
                {info.imsis.slice(0, 5).map((imsi, i) => (
                  <div key={i} className="flex items-center gap-2 text-[10px]">
                    <span className={`font-mono ${imsi.is_foreign ? "text-[#E63946]" : "text-[#06B6D4]"}`}>
                      {imsi.imsi}
                    </span>
                    <span className="text-[#6E7681]">{imsi.country}</span>
                    <span className="text-[#6E7681]">MCC {imsi.mcc}</span>
                    <span className="text-[#8B949E] font-mono ml-auto">{imsi.count}×</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[10px] text-[#6E7681] ml-2">No IMSI data</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function CellColocationSection({ data }) {
  if (!data) return null;
  if (!data.has_cell_data) {
    return (
      <div className="text-center py-6 text-[#6E7681]">
        <Radio className="w-8 h-8 mx-auto mb-2 opacity-30" />
        <p className="text-xs">No Cell-ID metadata available in uploaded records</p>
        <p className="text-[10px] mt-1">Co-location analysis requires CDR datasets with the cell_id / CGI / eCGI field.</p>
      </div>
    );
  }

  const events = data.events || [];
  const pairs = data.pair_summary || [];
  const cellCounts = data.subject_cell_counts || {};

  if (data.total_events === 0) {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {Object.entries(cellCounts).map(([s, c]) => (
            <div key={s} className="rounded-sm p-2 bg-[#0D0F14] border border-[#2D333B]">
              <div className="text-[9px] text-[#6E7681] uppercase tracking-wider">{s}</div>
              <div className="text-lg font-chivo font-bold text-[#A78BFA]">{c}</div>
              <div className="text-[9px] text-[#6E7681]">unique cells</div>
            </div>
          ))}
        </div>
        <p className="text-xs text-[#6E7681] text-center py-3">
          No co-location events detected. Subjects do not appear on the same cell tower within the ±5-minute window.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div className="rounded-sm p-2 bg-gradient-to-br from-[#A78BFA]/15 to-transparent border border-[#A78BFA]/30">
          <div className="text-[9px] text-[#A78BFA] uppercase tracking-wider font-chivo font-bold">Co-location Events</div>
          <div className="text-2xl font-chivo font-bold text-[#A78BFA]">{data.total_events}</div>
        </div>
        <div className="rounded-sm p-2 bg-[#0D0F14] border border-[#2D333B]">
          <div className="text-[9px] text-[#6E7681] uppercase tracking-wider">Subject Pairs</div>
          <div className="text-2xl font-chivo font-bold text-[#E1E7EF]">{pairs.length}</div>
        </div>
        {Object.entries(cellCounts).slice(0, 2).map(([s, c]) => (
          <div key={s} className="rounded-sm p-2 bg-[#0D0F14] border border-[#2D333B]">
            <div className="text-[9px] text-[#6E7681] uppercase tracking-wider truncate">{s}</div>
            <div className="text-lg font-chivo font-bold text-[#E1E7EF]">{c}</div>
            <div className="text-[9px] text-[#6E7681]">unique cells</div>
          </div>
        ))}
      </div>

      {/* Top pairs */}
      {pairs.length > 0 && (
        <div className="bg-[#090A0C] border border-[#2D333B] rounded-sm p-2">
          <div className="flex items-center gap-1.5 mb-2">
            <Users className="w-3 h-3 text-[#A78BFA]" />
            <span className="text-[10px] font-chivo font-bold text-[#E1E7EF] uppercase tracking-wider">
              Co-located Pairs
            </span>
          </div>
          <div className="space-y-1">
            {pairs.slice(0, 5).map((p, i) => (
              <div key={i} className="flex items-center gap-2 text-[10px] p-1.5 hover:bg-[#13151A] rounded-sm" data-testid="cell-pair-row">
                <div className="w-1 h-6 rounded-full bg-[#A78BFA]" />
                <span className="text-[#E1E7EF] font-mono">{p.pair}</span>
                <span className="text-[#6E7681]">·</span>
                <span className="text-[#A78BFA] font-mono">{p.unique_cells} cells</span>
                <span className="text-[#F59E0B] font-mono ml-auto">{p.count}× meets</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Events list */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] text-[#6E7681] uppercase tracking-wider font-chivo">
            Closest Co-location Events
          </span>
          <span className="text-[10px] text-[#8B949E]">
            Showing {Math.min(events.length, 15)} of {data.total_events}
          </span>
        </div>
        <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
          {events.slice(0, 15).map((ev, i) => {
            const diff = ev.time_diff_seconds;
            const tone =
              diff <= 60 ? { c: "#E63946", lbl: "SIMULTANEOUS" } :
              diff <= 180 ? { c: "#F59E0B", lbl: "VERY CLOSE" } :
              { c: "#FBBF24", lbl: "CLOSE" };
            return (
              <div
                key={i}
                className="rounded-sm border bg-[#0D0F14] overflow-hidden"
                style={{ borderColor: `${tone.c}30` }}
                data-testid="cell-event-card"
              >
                <div className="flex items-stretch">
                  <div className="w-1 flex-shrink-0" style={{ background: tone.c }} />
                  <div className="flex-1 p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge className="rounded-sm text-[9px] font-bold px-1.5 py-0 h-4" style={{ background: `${tone.c}20`, color: tone.c, borderColor: `${tone.c}40` }}>
                        {tone.lbl}
                      </Badge>
                      <span className="text-[10px] font-mono text-[#6E7681]">cell:</span>
                      <span className="text-[10px] font-mono text-[#A78BFA]">{ev.cell_id}</span>
                      <span className="text-[10px] font-mono ml-auto" style={{ color: tone.c }}>
                        {diff < 60 ? `${Math.round(diff)}s apart` : `${Math.floor(diff / 60)}m ${Math.round(diff % 60)}s apart`}
                      </span>
                    </div>
                    <div className="flex items-center gap-x-2 text-[10px] flex-wrap">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#0047FF]" />
                      <span className="text-[#E1E7EF] font-medium">{ev.subject1}</span>
                      <span className="text-[#6E7681] font-mono text-[9px]">{ev.timestamp1?.replace("T", " ").slice(0, 19)}</span>
                      <span className="text-[#2D333B]">↔</span>
                      <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                      <span className="text-[#E1E7EF] font-medium">{ev.subject2}</span>
                      <span className="text-[#6E7681] font-mono text-[9px]">{ev.timestamp2?.replace("T", " ").slice(0, 19)}</span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function BulkTransferSection({ data }) {
  if (!data) return null;
  if (!data.has_volume_data) {
    return (
      <div className="text-center py-6 text-[#6E7681]">
        <Upload className="w-8 h-8 mx-auto mb-2 opacity-30" />
        <p className="text-xs">No upload/download volume metadata available in uploaded IPDR records</p>
        <p className="text-[10px] mt-1">Bulk-transfer analysis requires IPDR datasets that include volume_up / volume_down fields.</p>
      </div>
    );
  }

  const perSubject = data.per_subject || {};
  const sharedHeavy = data.shared_heavy_platforms || [];

  return (
    <div className="space-y-3">
      {/* Per-subject panels */}
      {Object.entries(perSubject).map(([subject, info]) => {
        const totalAlerts = info.alert_count;
        const totalHigh = info.high_count;
        const totalMed = info.medium_count;
        const upload = info.total_up_human;
        const download = info.total_down_human;
        const sessions = info.top_sessions || [];
        const platforms = info.top_platforms || [];
        const uploadHeavy = info.upload_heavy_sessions || [];
        return (
          <div key={subject} className="bg-[#0D0F14] border border-[#2D333B] rounded-sm p-2" data-testid={`bulk-subject-${subject}`}>
            <div className="flex flex-wrap items-center gap-2 mb-2 pb-2 border-b border-[#2D333B]">
              <span className="text-xs font-medium text-[#E1E7EF]">{subject}</span>
              <div className="flex items-center gap-1 text-[10px]">
                <ArrowUpRight className="w-3 h-3 text-[#E63946]" />
                <span className="text-[#E63946] font-mono">{upload}</span>
              </div>
              <div className="flex items-center gap-1 text-[10px]">
                <ArrowDownRight className="w-3 h-3 text-[#10B981]" />
                <span className="text-[#10B981] font-mono">{download}</span>
              </div>
              <div className="ml-auto flex gap-1">
                {totalAlerts > 0 && (
                  <Badge className="rounded-sm text-[9px] bg-[#E6394620] text-[#E63946] border-[#E63946]/40">
                    {totalAlerts} ALERT
                  </Badge>
                )}
                {totalHigh > 0 && (
                  <Badge className="rounded-sm text-[9px] bg-[#F59E0B20] text-[#F59E0B] border-[#F59E0B]/40">
                    {totalHigh} HIGH
                  </Badge>
                )}
                {totalMed > 0 && (
                  <Badge className="rounded-sm text-[9px] bg-[#FBBF2420] text-[#FBBF24] border-[#FBBF24]/40">
                    {totalMed} MED
                  </Badge>
                )}
              </div>
            </div>

            {/* Top platforms by volume */}
            {platforms.length > 0 && (
              <div className="mb-2">
                <div className="text-[10px] text-[#6E7681] uppercase tracking-wider font-chivo mb-1">
                  Top Platforms by Volume
                </div>
                <div className="space-y-1">
                  {platforms.slice(0, 5).map((p, i) => {
                    const maxTotal = platforms[0].total_bytes || 1;
                    const widthPct = Math.max((p.total_bytes / maxTotal) * 100, 4);
                    return (
                      <div key={i} className="flex items-center gap-2" data-testid="bulk-platform-row">
                        <span className="text-[10px] text-[#E1E7EF] w-24 truncate font-mono">{p.platform}</span>
                        <div className="flex-1 h-3 bg-[#13151A] rounded-sm overflow-hidden relative">
                          <div
                            className="h-full bg-gradient-to-r from-[#E63946] to-[#F59E0B]"
                            style={{ width: `${widthPct}%`, transition: "width 600ms" }}
                          />
                        </div>
                        <span className="text-[10px] font-mono text-[#F59E0B] w-20 text-right">{p.total_human}</span>
                        <span className="text-[9px] font-mono text-[#6E7681] w-12 text-right">{p.sessions}×</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Top sessions (heaviest first) */}
            {sessions.length > 0 && (
              <div>
                <div className="text-[10px] text-[#6E7681] uppercase tracking-wider font-chivo mb-1">
                  Heaviest Sessions
                </div>
                <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                  {sessions.slice(0, 8).map((s, i) => {
                    const sevColor = s.severity === "ALERT" ? "#E63946" : s.severity === "HIGH" ? "#F59E0B" : "#FBBF24";
                    return (
                      <div
                        key={i}
                        className="flex items-center gap-2 text-[10px] p-1.5 rounded-sm bg-[#090A0C] border-l-2"
                        style={{ borderLeftColor: sevColor }}
                        data-testid="bulk-session-row"
                      >
                        <Badge className="rounded-sm text-[9px] px-1.5 py-0 h-4" style={{ background: `${sevColor}20`, color: sevColor, borderColor: `${sevColor}40` }}>
                          {s.severity}
                        </Badge>
                        <span className="font-mono text-[#E1E7EF]">{s.platform}</span>
                        <span className="text-[#6E7681] text-[9px] font-mono">{s.timestamp?.replace("T", " ").slice(0, 16)}</span>
                        <div className="flex items-center gap-1 ml-auto">
                          <ArrowUpRight className="w-2.5 h-2.5 text-[#E63946]" />
                          <span className="font-mono text-[#E63946]">{s.volume_up_human}</span>
                          <ArrowDownRight className="w-2.5 h-2.5 text-[#10B981] ml-1" />
                          <span className="font-mono text-[#10B981]">{s.volume_down_human}</span>
                          {s.is_upload_heavy && (
                            <ShieldAlert className="w-3 h-3 text-[#E63946] ml-1" title="Upload-heavy: possible exfiltration" />
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Upload-heavy callout */}
            {uploadHeavy.length > 0 && (
              <div className="mt-2 p-1.5 bg-[#E6394610] border border-[#E63946]/30 rounded-sm">
                <div className="flex items-center gap-1.5 text-[10px]">
                  <ShieldAlert className="w-3 h-3 text-[#E63946]" />
                  <span className="text-[#E63946] font-bold uppercase tracking-wider text-[9px]">
                    {uploadHeavy.length} upload-heavy session{uploadHeavy.length !== 1 ? "s" : ""} (upload ≥ 3× download)
                  </span>
                  <span className="text-[#8B949E] ml-auto">— possible data exfiltration</span>
                </div>
              </div>
            )}

            {sessions.length === 0 && platforms.length === 0 && (
              <p className="text-xs text-[#6E7681]">No high-volume sessions detected for {subject}</p>
            )}
          </div>
        );
      })}

      {/* Cross-subject heavy-platform sharing */}
      {sharedHeavy.length > 0 && (
        <div className="bg-[#E6394610] border border-[#E63946]/30 rounded-sm p-2">
          <div className="flex items-center gap-1.5 mb-2">
            <ShieldAlert className="w-3 h-3 text-[#E63946]" />
            <span className="text-[10px] font-chivo font-bold text-[#E63946] uppercase tracking-wider">
              Shared Heavy-Use Platforms (cross-subject)
            </span>
          </div>
          <div className="space-y-1">
            {sharedHeavy.map((s, i) => (
              <div key={i} className="text-[10px] p-1.5 bg-[#0D0F14] rounded-sm" data-testid="shared-heavy-row">
                <span className="font-mono text-[#F59E0B]">{s.platform}</span>
                <span className="text-[#8B949E] ml-2">— {s.inference}</span>
                <div className="text-[9px] text-[#6E7681] mt-0.5">
                  {s.subjects.map((u, j) => (
                    <span key={j}>{u.subject} ({u.total_human}){j < s.subjects.length - 1 ? " · " : ""}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AlertCard({ label, count, color, icon: Icon, desc, testId }) {
  return (
    <div
      className="rounded-sm p-2 border"
      style={{
        borderColor: `${color}40`,
        background: count > 0 ? `linear-gradient(135deg, ${color}20, transparent)` : "#0D0F14",
      }}
      data-testid={testId}
    >
      <div className="flex items-center justify-between">
        <span className="text-[9px] font-chivo font-bold uppercase tracking-wider" style={{ color }}>
          {label}
        </span>
        <Icon className="w-3 h-3" style={{ color, opacity: count > 0 ? 1 : 0.25 }} />
      </div>
      <div className="text-xl font-chivo font-bold mt-1" style={{ color }}>{count}</div>
      <div className="text-[9px] text-[#6E7681] leading-tight">{desc}</div>
    </div>
  );
}

function PriorityLeadsSection({ data }) {
  if (!data || !Array.isArray(data)) return null;
  return (
    <div className="space-y-1.5">
      {data.map((lead, i) => (
        <div key={i} className="p-2 bg-[#090A0C] border border-[#2D333B] rounded-sm">
          <div className="flex items-center gap-2 mb-1">
            <Badge className="rounded-sm text-[10px]" style={{ background: lead.priority === "HIGH" ? "#E6394620" : "#F59E0B20", color: lead.priority === "HIGH" ? "#E63946" : "#F59E0B" }}>
              {lead.priority}
            </Badge>
            <span className="text-[10px] uppercase text-[#6E7681]">{lead.type}</span>
            <span className="text-xs font-mono text-[#E1E7EF] ml-auto">{lead.value}</span>
          </div>
          <p className="text-[10px] text-[#8B949E]">{lead.action}</p>
        </div>
      ))}
      {data.length === 0 && <p className="text-xs text-[#6E7681]">No priority leads generated</p>}
    </div>
  );
}

function QuestionsSection({ data }) {
  if (!data) return null;
  return (
    <div className="space-y-3">
      {Object.entries(data).map(([subject, qs]) => (
        <div key={subject}>
          <p className="text-xs font-medium text-[#E1E7EF] mb-1 flex items-center gap-1">
            <HelpCircle className="w-3 h-3 text-[#F59E0B]" /> Questions for {subject}
          </p>
          <div className="space-y-1 ml-4">
            {qs.map((q, i) => (
              <p key={i} className="text-[10px] text-[#8B949E]">{i + 1}. {q}</p>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
