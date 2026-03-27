# ADR-016:

Plan: GPX Route Export (Client-Side, Multi-User Optimized)

1. Goal
   Implement GPX export entirely in the browser so users can download selected routes instantly without creating backend load, ensuring strong multi-user scalability.

2. Why this is optimal for multi-user performance
   No new server endpoint, no request queue, no serialization CPU on backend.
   Each user generates GPX locally from already-loaded route data.
   Export throughput scales with client devices, not server worker count.
   Works even if API is under heavy route-calculation load.
3. Architecture Decision
   Use a client-side GPX builder module that:

Reads selected route from in-memory state (routeState for standard routes, loopState for loops).
Serializes to GPX 1.1 XML.
Triggers download via Blob + URL.createObjectURL.
Includes optional metadata in GPX <extensions>.
No backend changes required for export itself.

Implementation Scope 4. Files to update
results_ui.js
Wire #export-gpx-btn click handling and selected-route resolution.
state.js
Fix loop selection key mismatch (selected vs selectedId) before export lookup.
app/static/js/modules/gpx_export.js (new)
GPX serialization + download utility.
index.html
Keep existing button; only add optional title/accessibility text if needed. 5. New module responsibilities (gpx_export.js)
buildGpxXml(routePayload):
Output valid GPX 1.1 with:
<gpx version="1.1" creator="ScenicPathFinder" ...>
<metadata> with route name + timestamp
<trk><name>...</name><trkseg>...
<trkpt lat="..." lon="..."> for all points
optional <ele> if elevation available
optional <extensions> for scenic stats
downloadGpx(xml, filename):
Create blob (application/gpx+xml;charset=utf-8)
Trigger download using temporary anchor
Revoke URL afterwards to avoid memory leaks
buildExportFilename(routeContext):
Example: scenicpathfinder-balanced-4.2km-2026-03-27.gpx 6. Export data contract (from existing frontend state)
Required:
route_coords ([[[lat, lon], ...]](http://vscodecontentref/14))
Optional:
stats.distance_km, stats.time_min
route label/type (balanced, baseline, extremist, loop label)
scenic scores/quality score when present
elevation if available from debug/edge data
If optional fields are absent, still produce valid GPX.

UI/UX Flow 7. Export button behavior
On click:
Resolve active route (standard selected route or selected loop).
Validate route exists and has at least 2 coordinates.
Build GPX XML.
Download file.
Show success toast.
Errors:
No selected route -> toast: “Select a route before exporting.”
Invalid route coords -> toast: “Route data unavailable for GPX export.” 8. Compatibility target
Generated GPX must import cleanly in:

Komoot
gpx.studio
Garmin Connect / Strava (basic track import)
Use track format (trk/trkseg/trkpt) for maximum compatibility.

Performance + Lightweight Guarantees 9. Performance characteristics
Time complexity: O(n) over route points.
Typical routes: fast enough for instant download (<100ms to low hundreds on common hardware).
Server impact: zero additional CPU/memory/network round-trips. 10. Lightweight principles
No new Python dependency (gpxpy not required).
No new backend API endpoint.
Pure JS + browser Blob APIs only.
Keep XML generation minimal and standards-compliant.
Verification Plan 11. Functional tests
Standard mode:
Export balanced, baseline, extremist.
Loop mode:
Export selected loop candidate.
Empty state:
Button clicked before route exists.
Edge cases:
Very short routes (2 points)
Large routes (many points) 12. Compatibility tests
Import downloaded file into gpxstudio.
Confirm path shape and metadata presence.
Spot-check with Komoot/Garmin format acceptance. 13. Regression checks
Ensure export action does not affect map rendering or selected route state.
Ensure memory cleanup (URL.revokeObjectURL) after download.
Handoff Acceptance Criteria
Clicking Export GPX downloads a .gpx for the currently selected route/loop.
File opens as valid GPX 1.1 in at least gpxstudio.
No backend changes are required for export workflow.
Export remains responsive under simultaneous use by many users (client-side scaling).
Missing optional metadata does not break export.
Delivery sequence (recommended)
Fix loopState selected key consistency.
Add gpx_export.js.
Wire button click in results_ui.js.
Add toasts and filename formatting.
Run manual compatibility tests and document sample outputs.
