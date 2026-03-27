# GPX Export Feature

## Overview

The GPX Export feature allows users to instantly download a `.gpx` file for their currently selected route (in standard routing) or round-trip loop. The exported files are compatible with popular third-party routing devices and services like Komoot, Strava, and Garmin Connect, and they encode both geographic points and relevant meta-information such as the route name, scenic scores, and path distances.

## Architecture & Implementation Principles

As detailed in the implementation plan, the GPX Export feature utilises a **client-side only architecture**. This is a deliberate design choice prioritizing user scale and backend efficiency.

Instead of an API endpoint taking route IDs, looking up the route, generating XML via an external library like `gpxpy`, and streaming it back to the client, **the entire GPX construction is done in the browser**.

### How it Works

1. **State Resolution**: When the "Export GPX" button is clicked in the UI, `getCurrentExportContext()` inside `results_ui.js` interrogates the in-memory route state (`routeState` or `loopState`). It fetches the exact coordinate history and metadata already retrieved to draw the route on the map.
2. **Naming Convention**: `getCurrentExportContext()` infers descriptive metadata based on the underlying states (`startState`, `endState`). It extracts concise location markers and attempts to establish the broader "Area" by matching shared portions of the reverse-geocoded addresses between the Start and End points. This drives the XML `<name>` field (e.g. `Start -> End | Distance`) and the filename format.
3. **XML Generation (`gpx_export.js`)**: The `buildGpxXml` function operates as a synchronous generator. For each `[lat, lon, ele?]` array in the route geometry, it emits standard `<trkpt>` lines. It additionally bundles ScenicPathFinder-specific metadata (such as `distance_km`, `time_min`, `quality_score`, `scenic_score`) into the `<extensions>` block for diagnostic or advanced use cases.
4. **Blob Download**: Having produced an XML string, `downloadGpx` takes over by wrapping the string inside a typed `Blob` (`application/gpx+xml;charset=utf-8`). The browser’s native `URL.createObjectURL` is invoked to create a temporary, locally-navigable link. A hidden anchor tag (`<a>`) is added to the DOM, programmatically "clicked", and then completely expunged with garbage collection freeing the object URL layout.

## Efficiency & Concurrency Benefits

### Why the feature is exceptionally efficient

- **No Network I/O**: Generating and downloading a GPX costs zero active network requests. The payload is materialized directly from data already seated in client memory. This significantly decreases perceived UI latency from "click" to "download".
- **Constant Time Transformation**: Converting a JSON array of `[[lat, lon], ...]` to XML string elements is exceedingly cheap. In browser engines, `Array.map().join("")` effectively constructs large markup bodies with negligible computational footprint ($O(n)$ time complexity relative to the number of route points).
- **Reduced Backend Liability**: There are no dependencies to manage server-side. No `gpxpy` overhead, no serialization overhead, and no bandwidth wasted shifting Megabytes of formatted XML over the wire. This drastically cuts down on computing costs for simple data retrieval.

### How it solves concurrency & scalability

In a multi-user environment (e.g., massive traffic due to concurrent user routing simulations), server resources must be ruthlessly guarded to preserve the responsiveness of the A\* Celery workers.

By forcing GPX export down to the client device:

- **Throughput Scales with Users**: The rendering mechanism scales linearly and effortlessly with the number of user devices. If 1,000 users click "Export GPX" simultaneously, 1,000 client browsers calculate the XML instantly. There is no centralized bottleneck or serialization queue.
- **Resilience to Heavy Load**: If the core routing backend is strained or offline while a user is dwelling on an available route, they can still successfully preserve their route progress. Download requests can never time-out or fail due to server sluggishness.

## Alignment with the Implementation Plan

The finished feature rigorously satisfies all facets of the provided `implementation_plan.md`:

- **Pure JS + Browser Blob APIs**: The export strictly relies on `Blob` and native URL APIs, meaning 0 new server dependencies were introduced.
- **Required Data Contracts**: Extracted the `route_coords` array seamlessly, supporting routes with two constraints all the way up to immense coordinate sequences.
- **Valid GPX 1.1 Specs**: Uses correct bounding and namespace identifiers ensuring wide third-party compatibility (e.g., `<gpx version="1.1">`, `xmlns`, `<trkpt>`, `<extensions>`).
- **Graceful Fault Tolerance**: Properly handles situations where optional parameters (like specific `quality_score` variables) are null, or when the user invokes the export button before routing variables exist.
- **User Experience Enhancements**: Handled filename synthesis dynamically utilizing Start, End, and Area variables (`scenicpathfinder-start-to-end-area-5.2km-YYYY-MM-DD.gpx`), providing highly contextual local file saving rather than a generic export naming scheme.
