Refactor Scenic Preferences and WSM Logic
Goal Description
Refactor the scenic routing preferences in the UI and the underlying WSM algorithm to be more intuitive.

UI: Replace "Prefer Flat" and "Social/POIs" sliders with toggles.
UI: Add a "Group Nature" toggle that combines "Greenery" and "Water" into a single "Nature" slider.
Algorithm: When "Group Nature" is active, uses a MAX benefit logic (conceptually MIN(cost_green, cost_water)) to treat them as a single "Nature" feature in the Weighted Sum Model.
User Review Required
IMPORTANT

WSM Logic Change: When "Group Nature" is enabled, the algorithm will use min(norm_green, norm_water) as the cost for the "Nature" component. This effectively selects the best feature score for each edge (since 0 is the best score). This aligns with the user's request to "pick the MAX of either... so it turns into 'Scenery'".

Proposed Changes
Backend
[MODIFY]
cost_calculator.py
Update
cost_wsm_additive
to accept combine_nature (bool).
Logic:
python
if combine_nature: # User wants "Nature" (best of green/water)
cost += \_calculate_nature_cost(norm_green, norm_water, weights['greenness'])
else:
cost += weights['greenness'] _ norm_green
cost += weights['water'] _ norm_water
Add helper method \_calculate_nature_cost(norm_green, norm_water, weight):
python
def \_calculate_nature_cost(norm_green, norm_water, weight):
"""
Combine green and water scores into a single nature score (best of both).
""" # Logic: min(norm_green, norm_water) uses the best score (lower is better)
nature_cost = min(norm_green, norm_water)
return weight \* nature_cost
Update
compute_cost
to pass combine_nature through.
[MODIFY]
wsm_astar.py
Update
init
to accept combine_nature (default False) and store it.
Update
distance_between
to pass self.combine_nature to
compute_wsm_cost
.
[MODIFY]
route_finder.py
Update
find_route
to accept combine_nature argument.
Pass it when initializing
WSMNetworkXAStar
.
[MODIFY]
routes.py
In
calculate_route
, extract combine_nature from request JSON data.
Pass it to RouteFinder.find_route (and find_distinct_paths if applicable).
Frontend
[MODIFY]
index.html
Add "Group Nature" toggle switch at the top of the scenic section.
Create a container for the "Nature" slider (initially hidden).
Change "Social/POIs" and "Prefer Flat" inputs from type="range" to styled checkbox toggles labeled "Prefer Social Areas" and "Prefer Flat".
[MODIFY]
main.js
Add event listener for "Group Nature" toggle.
Toggles visibility between [Greenery + Water sliders] and [Nature slider].
Update
getScenicWeights
:
Check "Group Nature" toggle:
If ON: Read Nature slider, set weights.greenness = val, weights.water = 0.
If OFF: Read Greenery and Water sliders as normal.
Read "Social" and "Flat" toggles:
If CHECKED: Set weight to 5 (max).
If UNCHECKED: Set weight to 0.
Add combine_nature flag to the API payload.
Verification Plan
Automated Tests
Run existing tests to ensure no regression in basic routing: python -m pytest tests/

Manual Verification
Start the server: python run.py
Open Browser: Go to http://localhost:5000
Test Toggles:
Verify "Prefer Flat" and "Social" are now toggles.
Enable "Prefer Flat". Calculate route. Verify in debug info that weights['slope'] is high (near 1.0 normalized) or effectively 5/total.
Test Grouping:
Enable "Group Green & Water".
Verify Greenery/Water sliders disappear and "Nature" slider appears.
Set Nature to MAX.
Calculate a route near water.
Verify Logic:
Check debug logs (terminal) or API debug info.
Ensure combine_nature is True in the request/logs.
Ensure the route favors water (because min(green, water) uses the best score).
Test Ungrouped:
Disable Grouping.
Set Greenery MAX, Water MIN.
Calculate route.
Verify it prefers Greenery specifically.
