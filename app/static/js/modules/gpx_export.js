/**
 * GPX Export Utilities (client-side)
 */

function escapeXml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function toNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function buildExportFilename(routeContext = {}) {
  const date = new Date().toISOString().slice(0, 10);
  const label = (routeContext.label || "route")
    .toString()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  const distance = toNumber(routeContext.distanceKm);
  const distancePart = distance !== null ? `-${distance.toFixed(1)}km` : "";
  return `scenicpathfinder-${label || "route"}${distancePart}-${date}.gpx`;
}

export function buildGpxXml(routePayload = {}) {
  const coords = Array.isArray(routePayload.route_coords)
    ? routePayload.route_coords
    : [];
  const name = routePayload.name || "ScenicPathFinder Route";
  const timeIso = new Date().toISOString();
  const distanceKm = toNumber(routePayload.stats?.distance_km);
  const timeMin = toNumber(routePayload.stats?.time_min);
  const quality = toNumber(routePayload.quality_score);
  const scenic = toNumber(routePayload.scenic_score);

  const trkPoints = coords
    .map((point) => {
      if (!Array.isArray(point) || point.length < 2) return "";
      const lat = toNumber(point[0]);
      const lon = toNumber(point[1]);
      if (lat === null || lon === null) return "";
      const ele = point.length > 2 ? toNumber(point[2]) : null;
      const eleTag = ele !== null ? `<ele>${ele}</ele>` : "";
      return `<trkpt lat="${lat}" lon="${lon}">${eleTag}</trkpt>`;
    })
    .join("");

  const extensionParts = [];
  if (distanceKm !== null) extensionParts.push(`<spf:distance_km>${distanceKm}</spf:distance_km>`);
  if (timeMin !== null) extensionParts.push(`<spf:time_min>${timeMin}</spf:time_min>`);
  if (quality !== null) extensionParts.push(`<spf:quality_score>${quality}</spf:quality_score>`);
  if (scenic !== null) extensionParts.push(`<spf:scenic_score>${scenic}</spf:scenic_score>`);

  const extensions = extensionParts.length
    ? `<extensions>${extensionParts.join("")}</extensions>`
    : "";

  return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="ScenicPathFinder" xmlns="http://www.topografix.com/GPX/1/1" xmlns:spf="https://scenicpathfinder.local/schema">
  <metadata>
    <name>${escapeXml(name)}</name>
    <time>${timeIso}</time>
  </metadata>
  <trk>
    <name>${escapeXml(name)}</name>
    ${extensions}
    <trkseg>${trkPoints}</trkseg>
  </trk>
</gpx>`;
}

export function downloadGpx(xml, filename) {
  const blob = new Blob([xml], { type: "application/gpx+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
