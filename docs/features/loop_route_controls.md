# Loop Route Controls

ScenicPathFinder's loop (round-trip) routing mode offers several controls
that let you tailor your route to your needs. These controls appear in the
sidebar when the **Loop** routing mode is selected.

> All controls are **optional** — with everything at default the solver
> produces a scenic loop using the Weighted Sum Model (greenness, water,
> quietness, social, elevation).

---

## Direction Bias

**UI label:** _compass buttons (N / S / E / W / None)_

Steers the overall shape of the loop toward a compass direction. For
example, clicking **North** biases the outbound leg northward, so the loop
bulges in that direction before returning to the start.

| Setting           | Effect                                                                |
| ----------------- | --------------------------------------------------------------------- |
| None (centre dot) | No directional preference — loop shape determined entirely by scenery |
| N / S / E / W     | Route is gently pushed in the chosen direction                        |

**When to use:** You know the scenic area is to the west of your start point
and want to ensure the loop heads that way rather than east.

---

## Prefer Paths & Trails

**UI label:** _Prefer paths & trails_ (toggle)

When enabled, the solver **strongly favours dedicated walking
infrastructure** — footpaths, tracks, bridleways, and pedestrian zones —
over roads shared with motor traffic.

Roads are penalised based on their OpenStreetMap `highway` tag:

| Road type                                                    | Penalty            |
| ------------------------------------------------------------ | ------------------ |
| Footway, path, pedestrian, cycleway, track, bridleway, steps | × 1.0 (no penalty) |
| Residential, living street, service road                     | × 1.2              |
| Unclassified, tertiary                                       | × 1.5              |
| Secondary                                                    | × 2.0              |
| Primary                                                      | × 2.5              |
| Trunk, motorway                                              | × 3.0              |

**When to use:** You are walking in a suburban or rural area and want the
route to stick to off-road paths and quiet lanes rather than following main
roads, even if the main roads have higher scenic scores.

---

## Prefer Paved Surfaces

**UI label:** _Prefer paved surfaces_ (toggle)

When enabled, the solver penalises edges with soft or uneven surfaces,
steering the route toward asphalt, concrete, and other hard surfaces.

| Surface type     | Examples                          | Penalty |
| ---------------- | --------------------------------- | ------- |
| Hard paved       | Asphalt, concrete, paving stones  | × 1.0   |
| Firm             | Sett, cobblestone, metal, wood    | × 1.1   |
| Compact unpaved  | Compacted gravel, fine gravel     | × 1.3   |
| Soft / wet       | Dirt, mud, sand, grass, woodchips | × 2.0   |
| Unknown (no tag) | Many residential streets          | × 1.2   |

**When to use:**

- **Wheelchair or pushchair users** who need a firm, even surface.
- **After heavy rain** when muddy footpaths are impassable.
- **Casual walkers** who prefer clean shoes over scenic short-cuts through
  fields.

> The "unknown" penalty (× 1.2) is deliberately mild. Many paved urban
> streets simply lack a `surface` tag in OpenStreetMap, so they should not
> be heavily penalised.

---

## Prefer Lit Streets

**UI label:** _Prefer lit streets_ (toggle)

When enabled, the solver **actively rewards** well-lit streets and
penalises unlit ones. This is particularly useful for evening or night-time
walks.

| Lighting status                  | Penalty                                    |
| -------------------------------- | ------------------------------------------ |
| Lit (`yes`, `automatic`, `24/7`) | × 0.85 (**bonus** — cheaper than baseline) |
| Limited / disused                | × 1.3                                      |
| Not lit (`no`)                   | × 1.8                                      |
| Unknown (no tag)                 | × 1.2                                      |

Unlike the other toggles, lit streets receive a **bonus** (multiplier less
than 1.0) rather than just penalising unlit ones. This ensures
well-lit residential streets can compete with scenic but dark park paths.

**When to use:**

- **Evening / night walks** when personal safety is a priority.
- **Combined with "Prefer paths & trails"** for a safety-first profile:
  footpaths are preferred, but only when they are lit.

> Lighting data (`lit` tag) is well covered in urban centres but sparse in
> rural areas, where the "unknown" penalty may gently push routes toward
> main roads that have streetlights.

> **Mutual exclusivity:** Enabling _Heavily avoid unlit streets_ (below)
> automatically unchecks this toggle since the stronger mode supersedes it.

---

## Heavily Avoid Unlit Streets

**UI label:** _Heavily avoid unlit streets_ (toggle, moon icon)

A much stronger version of "Prefer lit streets". The solver treats
confirmed-unlit streets as near-impassable — they receive a **× 5.0
cost penalty** — and streets with no lighting data are penalised at
**× 3.0**. Well-lit streets remain actively rewarded with a **× 0.70
bonus**.

| Lighting status                  | Multiplier                  |
| -------------------------------- | --------------------------- |
| Lit (`yes`, `automatic`, `24/7`) | × 0.70 (**strong bonus**)   |
| Limited / disused                | × 2.5                       |
| Not lit (`no`)                   | × 5.0 (**near-impassable**) |
| Unknown (no tag)                 | × 3.0 (assumed dark)        |

The × 5.0 penalty on a confirmed-unlit edge means the router will only
use it if there is genuinely no other viable way to reach the goal —
equivalent to treating it as five times the length it physically is.

Streets missing a `lit` tag are treated **conservatively as likely unlit**
(× 3.0), because many residential streets and footpaths in rural areas
have no lighting data but are genuinely unlit at night.

**When to use:**

- **Night-time safety** where personal security is the primary concern
  and scenic value is secondary.
- **Areas with more OSM lighting data** (city centres) where the ×3.0
  unknown penalty is less likely to eliminate otherwise valid paths.

> **Mutual exclusivity:** Enabling this toggle automatically unchecks
> "Prefer lit streets". Both cannot be active simultaneously; this mode
> always takes precedence.

> **Loop mode**: When used in GeometricLoopSolver (round-trip routing), the
> strong penalties can cause routed legs to be significantly longer than
> their air-line distance as the solver detours to stay on lit streets.
> This triggers the tortuosity (τ) feedback loop to shrink the geometric
> skeleton — see the [Street Lighting routing docs](street_lighting_routing_bias.md#loop-flow)
> for a full explanation.

---

## Avoid Unsafe Roads

**UI label:** _Avoid unsafe roads_ (toggle)

When enabled, the solver applies a **heavy penalty (× 3.5)** to primary,
secondary, and tertiary roads that lack pedestrian safety features.

A road is considered **unsafe** when:

1. Its `highway` tag is `primary`, `secondary`, or `tertiary` (or their
   `_link` variants), **and**
2. It has **no** `sidewalk` tag indicating a pavement (`both`, `left`,
   `right`, `yes`, or `separate`), **and**
3. It has **no** `foot` tag confirming pedestrian access (`yes` or
   `designated`).

If a road _does_ have a sidewalk or confirmed foot access, it keeps its
normal cost — the toggle only targets roads that are genuinely dangerous
for pedestrians.

**When to use:**

- **Walking with children** along roads that may have fast traffic.
- **Unfamiliar areas** where you want to avoid being forced onto a dual
  carriageway with no pavement.
- **Combined with "Prefer paths & trails"** for maximum safety: the
  pedestrian toggle favours footpaths proportionally, while this toggle
  blocks the worst main roads entirely.

> Sidewalk tagging in OpenStreetMap is inconsistent — some roads that have a
> wide pavement in reality may be penalised because no one has mapped the
> sidewalk yet. If the route seems to avoid a road you know is safe, this
> toggle may be the cause.

---

## Route Variety

**UI label:** _Route Variety_ (slider, 0–3)

Controls how much randomness the solver injects into its search costs.
Running the same query multiple times with variety > 0 will produce
**different routes** each time.

| Level      | Noise  | Effect                                                       |
| ---------- | ------ | ------------------------------------------------------------ |
| 0 (Off)    | ± 0 %  | Deterministic — same result every time                       |
| 1 (Low)    | ± 3 %  | Slight variation, routes remain very scenic                  |
| 2 (Medium) | ± 6 %  | Noticeable variation, may trade a little scenery for novelty |
| 3 (High)   | ± 10 % | Strong variation, good for exploring new areas               |

**When to use:**

- **Repeat walkers** who want a fresh route from the same start point each
  day without manually adjusting direction bias.
- **Exploration** — set to level 3 to discover routes you would never have
  chosen yourself.

> At level 3, the route may occasionally be slightly less scenic than the
> optimal path, but the trade-off is variety.

---

## Combining Controls

The toggles are independent and can be mixed freely. Some useful
combinations:

| Profile               | Controls                                                        |
| --------------------- | --------------------------------------------------------------- |
| **Safety first**      | Prefer paths & trails + Avoid unsafe roads + Prefer lit streets |
| **Night walk**        | Prefer lit streets + Avoid unsafe roads                         |
| **Night walk strict** | Heavily avoid unlit streets + Avoid unsafe roads                |
| **Accessible**        | Prefer paved surfaces + Avoid unsafe roads                      |
| **Adventurous**       | Route variety 3, all toggles off                                |
| **Trail runner**      | Prefer paths & trails, all others off                           |

> **Note:** _Prefer lit streets_ and _Heavily avoid unlit streets_ are **mutually exclusive** — enabling one automatically disables the other in the UI.

Each toggle multiplies the edge cost independently. When multiple toggles
are enabled, their penalties **stack multiplicatively** — a dark, unsurfaced
main road with no pavement would receive × 5.0 (heavily unlit) × 2.0
(soft surface) × 3.5 (unsafe) = × 35.0, making it essentially
unroutable.
