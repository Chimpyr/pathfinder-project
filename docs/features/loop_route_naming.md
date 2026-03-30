# Loop Route Naming Scheme

This document defines how loop route candidates are named, explained, and exposed
through the API/UI.

It applies to loop responses returned by `POST /calculate_loop_route` and covers
both backend generation and frontend presentation.

---

## Goals

The naming system is designed to:

- Avoid generic numeric labels (for example, `Route 5`, `Route 6`).
- Give users a quick mental model of each option.
- Explain why each loop was selected.
- Keep API ids stable even if display labels change.
- Keep naming logic deterministic for a fixed candidate ordering.

---

## End-to-End Flow

1. Candidate loops are generated and ranked.
2. A diverse subset is selected (`select_diverse_candidates`).
3. Each selected candidate gets:
   - A primary display label (`label`),
   - A concise descriptor subtitle (`name_subtitle` -> `label_subtitle`),
   - A reason string (`name_reason` -> `label_reason`).
4. API response serializes these fields.
5. Frontend renders:
   - Label + subtitle + reason in loop cards,
   - Label + subtitle in map tooltip,
   - Label in saved-query default naming.

---

## Label Assignment

Labels are now assigned by role criteria, not pure index order.

Primary role labels:

- `Best Match`
- `Scenic Alternative`
- `Diverse Alternative`
- `Exploration Option`

Additional fallback labels (if more candidates remain):

- `Quiet Streets Option`
- `Extended Option`
- `Neighbourhood Option`
- `Panoramic Option`
- `Balanced Option`
- `Fallback Option`

Role selection logic for the selected candidate set:

1. `Best Match`: highest `quality_score` (already index 0 in selection).
2. `Scenic Alternative`: lowest `scenic_cost` among remaining candidates.
3. `Diverse Alternative`: highest edge dissimilarity vs `Best Match` among remaining candidates.
4. `Exploration Option`: highest average dissimilarity vs all other candidates among remaining candidates.
5. Any additional candidates receive fallback labels.

This keeps names descriptive and ties each key label to a measurable property.

---

## Subtitle Generation (`name_subtitle`)

Subtitle format:

- `<direction descriptor> | <shape descriptor>`

Example:

- `South-west | Triangle`

Direction descriptor source (`bearing` metadata):

- `north/east/south/west` strings map to `Northbound/Eastbound/...`.
- Numeric bearings are bucketed into 8 compass sectors.
- Missing or invalid values fall back to `Any direction`.

Shape descriptor source (`type` and `shape` metadata):

- `type == out-and-back` -> `Out-and-back`
- `shape == N=3` -> `Triangle`
- `shape == N=4` -> `Quadrilateral`
- `shape == N=5` -> `Pentagon`
- `shape == N=6` -> `Hexagon`
- `shape >= N=7` -> `Polygon`
- Unknown -> `Loop`

---

## Reason Generation (`name_reason`)

Reason text explains the role assignment with concrete metrics.

### Candidate 0 (Best Match)

Uses combined quality and target-distance fidelity:

- `Assigned as Best Match: highest combined quality score (<quality_score>) with <deviation_percent>% target deviation.`

### Candidate 1..N

Uses role-specific criteria with distance fidelity:

- `Scenic Alternative`: lowest scenic cost among alternatives + target deviation.
- `Diverse Alternative`: highest edge dissimilarity vs Best Match + target deviation.
- `Exploration Option`: high cross-route novelty (average dissimilarity across all options) + target deviation.
- Extra options: fallback balancing summary.

Where:

- Scenic rank is computed by sorting selected candidates by `scenic_cost` ascending.
- Dissimilarity is based on edge-level Jaccard similarity against the best match:
  - similarity = overlap(edges) / union(edges)
  - dissimilarity = `round((1 - similarity) * 100)`

---

## Explainability Tags (`name_tags`)

Each candidate also gets compact tags to make the naming rationale scannable in
the UI.

Typical tags include:

- Role criterion tag (for example, `Max edge diversity vs best`).
- `Target delta <x>%`
- `Scenic rank <r>/<n>`
- `<y>% different vs best` (non-best options)
- `Bias: <North/East/South/West>` when directional bias is active
- `Variety L<0-3>`
- `Smart bearing` when enabled

These tags are intended to answer "why this name" without requiring debug mode.

---

## API Contract

Loop candidates include:

- `id`: stable id in the format `loop-<index>-<slug(label)>`
- `label`: user-facing loop name
- `label_subtitle`: compact descriptor generated from geometry/direction
- `label_reason`: human-readable explainability sentence
- `label_role`: internal role token (`best_match`, `scenic_alternative`, etc.)
- `label_tags`: compact metric/settings tags backing the label choice
- `metadata`: retains raw naming metadata (`name_subtitle`, `name_reason`, strategy)

### Why id is decoupled from label

Display labels can evolve for UX reasons. Ids must remain predictable and unique
within the response, so ids are generated from index + slugified label, rather
than relying on a raw label transform alone.

---

## Frontend Presentation Rules

In the Routes panel (loop mode):

- Show `label` as the primary title.
- Show `label_subtitle` below the title when present.
- Show `label_tags` as compact chips when present.
- Show `label_reason` as small explanatory text when present.

On map tooltips:

- Show `label` and `label_subtitle`.

When saving queries:

- Default saved name format is `<loop label> from <start label>`.

---

## Example (Trimmed)

```json
{
  "loops": [
    {
      "id": "loop-1-best-match",
      "label": "Best Match",
      "label_subtitle": "South-west | Triangle",
      "label_tags": [
        "Quality leader",
        "Target delta 3.9%",
        "Scenic rank 1/4",
        "Variety L2"
      ],
      "label_reason": "Assigned as Best Match: highest combined quality score (0.579) with 3.9% target deviation."
    },
    {
      "id": "loop-2-scenic-alternative",
      "label": "Scenic Alternative",
      "label_subtitle": "North-west | Triangle",
      "label_tags": [
        "Lowest scenic cost (alt)",
        "Target delta 0.5%",
        "Scenic rank 2/4",
        "93% different vs best"
      ],
      "label_reason": "Assigned as Scenic Alternative: lowest scenic cost among alternatives (rank 2/4) with 0.5% target deviation."
    }
  ]
}
```

---

## Maintenance Guidance

If updating this scheme:

- Keep labels descriptive and non-numeric.
- Keep subtitle format short and scan-friendly.
- Keep reason strings factual and metric-backed.
- Preserve id stability principles (do not depend on mutable UI copy).
- Update this document whenever naming metadata fields or wording templates change.
