import { useMemo, useState, useRef, useEffect } from "react";

const NODE_COLORS = {
  subject: "#0047FF",
  platform: "#F59E0B",
  contact: "#8B949E",
};

const CAT_COLORS = {
  crypto: "#F59E0B",
  messaging: "#0047FF",
  file_transfer: "#10B981",
  social: "#A78BFA",
  vpn_proxy: "#E63946",
  email: "#06B6D4",
  contact: "#6E7681",
  anonymous_chat: "#FF6B6B",
  pakistan_isp: "#E63946",
  live_streaming: "#C084FC",
  unknown: "#6E7681",
};

const CAT_LABELS = {
  crypto: "Crypto",
  messaging: "Messaging",
  file_transfer: "File Transfer",
  social: "Social",
  vpn_proxy: "VPN/Proxy",
  email: "Email",
  anonymous_chat: "Anonymous Chat",
  pakistan_isp: "Pakistan ISP",
  live_streaming: "Live Streaming",
  unknown: "Other",
};

// Compute neighbor map for hover highlighting
function buildAdjacency(nodes, links) {
  const adj = {};
  nodes.forEach((n) => (adj[n.id] = new Set()));
  links.forEach((l) => {
    if (adj[l.source]) adj[l.source].add(l.target);
    if (adj[l.target]) adj[l.target].add(l.source);
  });
  return adj;
}

function computeLayout(data, width, height) {
  const cx = width / 2;
  const cy = height / 2;
  const positioned = {};

  const subjects = data.nodes.filter((n) => n.type === "subject");
  const platforms = data.nodes.filter((n) => n.type === "platform");
  const contacts = data.nodes.filter((n) => n.type === "contact");

  // Group platforms by category for clustering
  const platformsByCat = {};
  platforms.forEach((p) => {
    const cat = p.category || "unknown";
    if (!platformsByCat[cat]) platformsByCat[cat] = [];
    platformsByCat[cat].push(p);
  });
  const cats = Object.keys(platformsByCat);

  // Connection count for sizing
  const linkCount = {};
  data.links.forEach((l) => {
    linkCount[l.source] = (linkCount[l.source] || 0) + 1;
    linkCount[l.target] = (linkCount[l.target] || 0) + 1;
  });

  const minDim = Math.min(width, height);
  const r1 = minDim * 0.13; // subjects ring
  const r2 = minDim * 0.31; // platforms ring
  const r3 = minDim * 0.45; // contacts ring

  // Subjects: inner circle
  const sN = Math.max(subjects.length, 1);
  subjects.forEach((node, i) => {
    const angle = sN === 1 ? -Math.PI / 2 : (2 * Math.PI * i) / sN - Math.PI / 2;
    const conns = linkCount[node.id] || 0;
    positioned[node.id] = {
      ...node,
      x: cx + (sN === 1 ? 0 : r1 * Math.cos(angle)),
      y: cy + (sN === 1 ? 0 : r1 * Math.sin(angle)),
      radius: 22 + Math.min(conns, 12),
      color: NODE_COLORS.subject,
      connections: conns,
      angle,
    };
  });

  // Platforms: clustered by category in mid ring
  let platIndex = 0;
  const platTotal = platforms.length || 1;
  cats.forEach((cat, ci) => {
    const list = platformsByCat[cat];
    list.forEach((node, i) => {
      // Spread evenly across the full circle while clustering categories together
      const angle = (2 * Math.PI * platIndex) / platTotal - Math.PI / 2;
      const conns = linkCount[node.id] || 0;
      positioned[node.id] = {
        ...node,
        x: cx + r2 * Math.cos(angle),
        y: cy + r2 * Math.sin(angle),
        radius: 9 + Math.min(conns * 1.2, 6),
        color: CAT_COLORS[cat] || CAT_COLORS.unknown,
        connections: conns,
        angle,
      };
      platIndex += 1;
    });
  });

  // Contacts: outer ring, position near connected subjects
  const cN = Math.max(contacts.length, 1);
  contacts.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / cN - Math.PI / 2;
    const conns = linkCount[node.id] || 0;
    positioned[node.id] = {
      ...node,
      x: cx + r3 * Math.cos(angle),
      y: cy + r3 * Math.sin(angle),
      radius: 7 + Math.min(conns, 4),
      color: NODE_COLORS.contact,
      connections: conns,
      angle,
    };
  });

  return positioned;
}

// Quadratic bezier control point for gentle curves
function curvedPath(x1, y1, x2, y2, cx, cy) {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  // Pull control toward center for inner curve, push outward for outer curve
  const dx = mx - cx;
  const dy = my - cy;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  const offset = 22;
  const px = mx - (dy / dist) * offset;
  const py = my + (dx / dist) * offset;
  return `M ${x1} ${y1} Q ${px} ${py} ${x2} ${y2}`;
}

export default function NetworkGraph({ data }) {
  const containerRef = useRef(null);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 560 });

  useEffect(() => {
    const updateSize = () => {
      const container = containerRef.current;
      if (container) {
        const w = container.clientWidth;
        setDimensions({
          width: Math.max(w, 480),
          height: Math.max(Math.min(w * 0.62, 700), 460),
        });
      }
    };
    updateSize();
    window.addEventListener("resize", updateSize);
    return () => window.removeEventListener("resize", updateSize);
  }, []);

  const { layout, adjacency, categoryStats } = useMemo(() => {
    if (!data || !data.nodes || data.nodes.length === 0) {
      return { layout: null, adjacency: {}, categoryStats: {} };
    }
    const lay = computeLayout(data, dimensions.width, dimensions.height);
    const adj = buildAdjacency(data.nodes, data.links || []);
    const stats = {};
    data.nodes.forEach((n) => {
      if (n.type === "platform") {
        const cat = n.category || "unknown";
        stats[cat] = (stats[cat] || 0) + 1;
      }
    });
    return { layout: lay, adjacency: adj, categoryStats: stats };
  }, [data, dimensions]);

  if (!data || !data.nodes || data.nodes.length === 0) {
    return <p className="text-xs text-[#6E7681] text-center py-4">No relationship data available</p>;
  }
  if (!layout) return null;

  const subjectCount = data.nodes.filter((n) => n.type === "subject").length;
  const platformCount = data.nodes.filter((n) => n.type === "platform").length;
  const contactCount = data.nodes.filter((n) => n.type === "contact").length;

  const isFaded = (id) => hoveredNode && hoveredNode !== id && !adjacency[hoveredNode]?.has(id);
  const isLinkActive = (link) => !hoveredNode || hoveredNode === link.source || hoveredNode === link.target;

  return (
    <div ref={containerRef} data-testid="network-graph" className="w-full">
      {/* Stats bar */}
      <div className="flex flex-wrap gap-2 mb-2 text-[10px]">
        <span className="px-2 py-0.5 bg-[#0047FF]/10 border border-[#0047FF]/30 rounded-sm text-[#0047FF] font-mono">
          {subjectCount} SUBJECTS
        </span>
        <span className="px-2 py-0.5 bg-[#F59E0B]/10 border border-[#F59E0B]/30 rounded-sm text-[#F59E0B] font-mono">
          {platformCount} PLATFORMS
        </span>
        <span className="px-2 py-0.5 bg-[#8B949E]/10 border border-[#8B949E]/30 rounded-sm text-[#8B949E] font-mono">
          {contactCount} SHARED CONTACTS
        </span>
        <span className="px-2 py-0.5 bg-[#13151A] border border-[#2D333B] rounded-sm text-[#6E7681] font-mono">
          {data.links?.length || 0} CONNECTIONS
        </span>
      </div>

      <div className="relative bg-gradient-to-br from-[#090A0C] to-[#0D0F14] border border-[#2D333B] rounded-sm overflow-hidden">
        <svg
          width={dimensions.width}
          height={dimensions.height}
          className="w-full block"
          viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
        >
          <defs>
            {/* Drop shadow filter */}
            <filter id="nodeGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceAlpha" stdDeviation="3" />
              <feOffset dx="0" dy="0" result="offsetblur" />
              <feFlood floodColor="#0047FF" floodOpacity="0.5" />
              <feComposite in2="offsetblur" operator="in" />
              <feMerge>
                <feMergeNode />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="hoverGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceAlpha" stdDeviation="5" />
              <feFlood floodColor="#FFFFFF" floodOpacity="0.6" />
              <feComposite in2="SourceAlpha" operator="in" />
              <feMerge>
                <feMergeNode />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Radial gradient for subject nodes */}
            <radialGradient id="subjectGrad" cx="35%" cy="35%">
              <stop offset="0%" stopColor="#3B73FF" />
              <stop offset="100%" stopColor="#0047FF" />
            </radialGradient>

            {/* Concentric ring guides */}
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <circle cx="0" cy="0" r="1" fill="#1C1F26" />
            </pattern>
          </defs>

          <rect width={dimensions.width} height={dimensions.height} fill="url(#grid)" />

          {/* Concentric guide rings */}
          {[0.13, 0.31, 0.45].map((r, i) => (
            <circle
              key={i}
              cx={dimensions.width / 2}
              cy={dimensions.height / 2}
              r={Math.min(dimensions.width, dimensions.height) * r}
              fill="none"
              stroke="#1C1F26"
              strokeWidth={0.5}
              strokeDasharray="2 4"
            />
          ))}

          {/* Links */}
          <g>
            {data.links?.map((link, i) => {
              const source = layout[link.source];
              const target = layout[link.target];
              if (!source || !target) return null;
              const active = isLinkActive(link);
              const isContactLink = link.type === "contact";
              const linkColor = isContactLink ? "#8B949E" : target.color || "#2D333B";
              return (
                <path
                  key={i}
                  d={curvedPath(source.x, source.y, target.x, target.y, dimensions.width / 2, dimensions.height / 2)}
                  fill="none"
                  stroke={active ? linkColor : "#1C1F26"}
                  strokeWidth={active ? (hoveredNode ? 1.6 : 0.8) : 0.4}
                  strokeOpacity={active ? (hoveredNode ? 0.85 : 0.4) : 0.15}
                  strokeLinecap="round"
                  style={{ transition: "stroke 200ms, stroke-opacity 200ms, stroke-width 200ms" }}
                />
              );
            })}
          </g>

          {/* Nodes */}
          <g>
            {Object.values(layout).map((node) => {
              const isHovered = hoveredNode === node.id;
              const faded = isFaded(node.id);
              const opacity = faded ? 0.18 : 1;

              return (
                <g
                  key={node.id}
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                  style={{ cursor: "pointer", opacity, transition: "opacity 200ms" }}
                  data-testid={`graph-node-${node.id}`}
                >
                  {/* Outer halo on hover */}
                  {isHovered && (
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={node.radius + 10}
                      fill={node.color}
                      fillOpacity={0.18}
                    />
                  )}

                  {/* Main node circle */}
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={node.radius}
                    fill={node.type === "subject" ? "url(#subjectGrad)" : node.color}
                    fillOpacity={node.type === "subject" ? 1 : 0.85}
                    stroke={isHovered ? "#FFFFFF" : node.color}
                    strokeWidth={isHovered ? 2 : 1.2}
                    strokeOpacity={isHovered ? 1 : 0.7}
                    filter={node.type === "subject" ? "url(#nodeGlow)" : undefined}
                    style={{ transition: "stroke-width 200ms, stroke-opacity 200ms" }}
                  />

                  {/* Inner glyph for subjects */}
                  {node.type === "subject" && (
                    <text
                      x={node.x}
                      y={node.y + 4}
                      textAnchor="middle"
                      fill="#FFFFFF"
                      fontSize={Math.max(node.radius * 0.55, 11)}
                      fontFamily="Chivo, sans-serif"
                      fontWeight={800}
                      style={{ pointerEvents: "none", letterSpacing: "0.03em" }}
                    >
                      {node.label?.slice(0, 2).toUpperCase()}
                    </text>
                  )}

                  {/* Connection count badge for subjects */}
                  {node.type === "subject" && node.connections > 0 && (
                    <g style={{ pointerEvents: "none" }}>
                      <circle
                        cx={node.x + node.radius * 0.78}
                        cy={node.y - node.radius * 0.78}
                        r={9}
                        fill="#0D0F14"
                        stroke="#0047FF"
                        strokeWidth={1.2}
                      />
                      <text
                        x={node.x + node.radius * 0.78}
                        y={node.y - node.radius * 0.78 + 3}
                        textAnchor="middle"
                        fill="#0047FF"
                        fontSize={9}
                        fontFamily="IBM Plex Mono, monospace"
                        fontWeight={700}
                      >
                        {node.connections}
                      </text>
                    </g>
                  )}

                  {/* Label */}
                  <text
                    x={node.x}
                    y={node.y + node.radius + (node.type === "subject" ? 16 : 13)}
                    textAnchor="middle"
                    fill={isHovered ? "#FFFFFF" : node.type === "subject" ? "#E1E7EF" : "#8B949E"}
                    fontSize={node.type === "subject" ? 11 : 9}
                    fontFamily="IBM Plex Mono, monospace"
                    fontWeight={node.type === "subject" ? 700 : 500}
                    style={{ pointerEvents: "none", letterSpacing: node.type === "subject" ? "0.05em" : "0" }}
                  >
                    {node.label?.length > 16 ? node.label.slice(0, 16) + "…" : node.label}
                  </text>

                  {/* Category mini-tag for platforms (only on hover for less clutter) */}
                  {node.type === "platform" && isHovered && node.category && (
                    <text
                      x={node.x}
                      y={node.y + node.radius + 24}
                      textAnchor="middle"
                      fill={node.color}
                      fontSize={8}
                      fontFamily="IBM Plex Sans, sans-serif"
                      fontWeight={600}
                      style={{ pointerEvents: "none", textTransform: "uppercase", letterSpacing: "0.1em" }}
                    >
                      {CAT_LABELS[node.category] || node.category}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        {/* Hover tooltip */}
        {hoveredNode && layout[hoveredNode] && (
          <div
            className="absolute pointer-events-none bg-[#0D0F14] border border-[#2D333B] rounded-sm px-2 py-1.5 shadow-lg"
            style={{
              left: Math.min(layout[hoveredNode].x + 18, dimensions.width - 180),
              top: Math.max(layout[hoveredNode].y - 30, 8),
              fontSize: 10,
              minWidth: 140,
            }}
          >
            <div className="text-[#E1E7EF] font-mono font-bold">{layout[hoveredNode].label}</div>
            <div className="text-[#6E7681] text-[9px] uppercase tracking-wider mt-0.5">
              {layout[hoveredNode].type}
              {layout[hoveredNode].category && ` · ${CAT_LABELS[layout[hoveredNode].category] || layout[hoveredNode].category}`}
            </div>
            <div className="text-[#0047FF] text-[9px] font-mono mt-1">
              {layout[hoveredNode].connections} connection{layout[hoveredNode].connections !== 1 ? "s" : ""}
            </div>
          </div>
        )}

        {/* Legend - bottom-left */}
        <div className="absolute left-2 bottom-2 bg-[#0D0F14]/85 backdrop-blur-sm border border-[#2D333B] rounded-sm p-2 max-w-[55%]">
          <div className="text-[9px] text-[#6E7681] uppercase tracking-wider mb-1 font-chivo">Legend</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
            <LegendDot color={NODE_COLORS.subject} label="Subject" filled />
            <LegendDot color={NODE_COLORS.contact} label="Shared Contact" />
            {Object.entries(categoryStats)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 8)
              .map(([cat, count]) => (
                <LegendDot key={cat} color={CAT_COLORS[cat] || CAT_COLORS.unknown} label={`${CAT_LABELS[cat] || cat} (${count})`} />
              ))}
          </div>
        </div>

        {/* Help hint - top-right */}
        <div className="absolute right-2 top-2 text-[9px] text-[#6E7681] font-mono">
          hover a node to highlight relationships
        </div>
      </div>
    </div>
  );
}

function LegendDot({ color, label, filled }) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="inline-block w-2 h-2 rounded-full flex-shrink-0"
        style={{
          background: color,
          boxShadow: filled ? `0 0 6px ${color}` : "none",
          opacity: filled ? 1 : 0.85,
        }}
      />
      <span className="text-[9px] text-[#8B949E] font-mono whitespace-nowrap">{label}</span>
    </div>
  );
}
