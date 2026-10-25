import { useMemo } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Fix Leaflet default marker icons (webpack breaks them)
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

const SUBJECT_COLORS = ["#0047FF", "#E63946", "#10B981", "#F59E0B", "#A78BFA", "#FF6B6B"];

function createSubjectIcon(color) {
  return new L.DivIcon({
    className: "",
    html: `<div style="
      width:28px;height:28px;border-radius:50%;
      background:${color};border:3px solid #E1E7EF;
      box-shadow:0 2px 8px rgba(0,0,0,0.5);
      display:flex;align-items:center;justify-content:center;
    "><div style="width:8px;height:8px;border-radius:50%;background:#fff;"></div></div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -16],
  });
}

export default function LocationMap({ data }) {
  const points = useMemo(() => {
    const geo = data?.geocoded || {};
    return Object.entries(geo).map(([subject, coords], i) => ({
      subject,
      position: [coords.lat, coords.lng],
      display: coords.display,
      location: coords.location,
      color: SUBJECT_COLORS[i % SUBJECT_COLORS.length],
    }));
  }, [data]);

  const center = useMemo(() => {
    if (points.length === 0) return [28.6, 77.2]; // fallback: Delhi
    return [
      points.reduce((s, p) => s + p.position[0], 0) / points.length,
      points.reduce((s, p) => s + p.position[1], 0) / points.length,
    ];
  }, [points]);

  const lines = useMemo(() => {
    const comps = data?.comparisons || [];
    const result = [];
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const comp = comps.find(
          (c) => c.subjects.includes(points[i].subject) && c.subjects.includes(points[j].subject)
        );
        result.push({
          positions: [points[i].position, points[j].position],
          distance: comp?.distance_km,
          note: comp?.note,
        });
      }
    }
    return result;
  }, [points, data]);

  if (points.length === 0) {
    return (
      <div className="text-center py-6 border border-dashed border-[#2D333B] rounded-sm">
        <p className="text-xs text-[#6E7681]">No geocoded locations available.</p>
        <p className="text-[10px] text-[#6E7681] mt-1">Add location data to subjects for map visualization.</p>
      </div>
    );
  }

  return (
    <div data-testid="location-map" className="space-y-2">
      <div className="w-full h-72 rounded-sm overflow-hidden border border-[#2D333B]">
        <MapContainer
          center={center}
          zoom={points.length === 1 ? 12 : 7}
          className="w-full h-full"
          style={{ background: "#090A0C" }}
          scrollWheelZoom={true}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
          />

          {points.map((p) => (
            <Marker key={p.subject} position={p.position} icon={createSubjectIcon(p.color)}>
              <Popup>
                <div style={{ fontFamily: "IBM Plex Sans, sans-serif", fontSize: 12, lineHeight: 1.5 }}>
                  <strong style={{ color: p.color }}>{p.subject}</strong>
                  <br />
                  <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 11 }}>{p.location}</span>
                  <br />
                  <span style={{ fontSize: 10, color: "#666" }}>{p.display}</span>
                  <br />
                  <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 10, color: "#888" }}>
                    {p.position[0].toFixed(4)}, {p.position[1].toFixed(4)}
                  </span>
                </div>
              </Popup>
            </Marker>
          ))}

          {lines.map((line, i) => (
            <Polyline
              key={i}
              positions={line.positions}
              color="#0047FF"
              weight={2}
              dashArray="6,4"
              opacity={0.7}
            />
          ))}
        </MapContainer>
      </div>

      {/* Distance legend below map */}
      <div className="flex flex-wrap gap-3">
        {points.map((p) => (
          <div key={p.subject} className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-full" style={{ background: p.color, border: "1.5px solid #E1E7EF" }} />
            <span className="text-[10px] text-[#E1E7EF]">{p.subject}</span>
            <span className="text-[10px] font-mono text-[#6E7681]">{p.location}</span>
          </div>
        ))}
      </div>

      {lines.filter((l) => l.distance != null).map((l, i) => (
        <div key={i} className="flex items-center gap-2 p-1.5 bg-[#090A0C] rounded-sm text-[10px]">
          <div className="w-6 border-t border-dashed border-[#0047FF]" />
          <span className="text-[#8B949E]">{l.note}</span>
          {l.distance != null && (
            <span className="font-mono text-[#F59E0B] ml-auto">{l.distance} km</span>
          )}
        </div>
      ))}
    </div>
  );
}
