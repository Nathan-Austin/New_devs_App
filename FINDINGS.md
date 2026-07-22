# Revenue Dashboard Investigation: Findings and Fixes

This document summarizes the bugs found while investigating the issues reported
by Client A, Client B, and the finance team, and the fixes applied for each.
See the git history for the full commit-by-commit detail; this is the
condensed version.

## How the investigation started

Before touching any code, the environment was brought up with
`docker-compose up --build` and both client accounts were logged in through
the actual API (`/api/v1/auth/login`) to reproduce the reported symptoms
directly, rather than guessing from reading code alone.

## Bug 1: Database connection pool never actually connected

**Symptom:** Every property, for every tenant, returned the same fixed
numbers regardless of which client or property was requested.

**How found:** Backend logs showed `Database pool initialization failed:
'Settings' object has no attribute 'supabase_db_user'` on every request.
`calculate_total_revenue` caught that exception and silently fell back to a
hardcoded mock dataset, so the API never actually failed, it just quietly
returned fake numbers.

**Root cause:** `backend/app/core/database_pool.py` built its connection
string from settings fields (`supabase_db_user`, `supabase_db_host`, etc.)
that do not exist anywhere in `config.py`. There was also an invalid
`poolclass=QueuePool` argument incompatible with an async engine, and
`get_session()` was a plain coroutine being used with `async with`, which
fails at runtime.

**Fix:** Build the connection string from the actual `database_url` setting
(which docker-compose already sets correctly), drop the invalid pool class,
and make `get_session()` a real async context manager.

**Why it mattered:** Until this was fixed, none of the other three bugs were
even visible through the running app, since every request was served from
static mock data instead of the real database.

## Bug 2: Revenue cache leaked data across tenants

**Symptom (Client B):** "Sometimes when we refresh the page, we see revenue
numbers that look like they belong to another company."

**How found:** The seed data has two different properties that share the id
`prop-001` (one per tenant). Logging in as Client A and requesting `prop-001`,
then immediately logging in as Client B and requesting their own `prop-001`,
returned Client A's numbers.

**Root cause:** `backend/app/services/cache.py` built the Redis cache key as
`f"revenue:{property_id}"`, with no tenant scoping. Since property ids are
not unique across tenants, whichever tenant asked first populated a cache
entry the other tenant could then read.

**Fix:** Cache key now includes `tenant_id`: `f"revenue:{tenant_id}:{property_id}"`.

**Verified:** Client A requests `prop-001` (populates cache), Client B
immediately requests their own `prop-001` and correctly gets their own data,
confirmed repeatedly across refreshes and confirmed by inspecting the Redis
keys directly (two separate keys, one per tenant).

## Bug 3: Revenue totals could round down a cent

**Symptom (finance team):** Totals "slightly off by a few cents," not
reproducible on demand.

**How found:** `total_amount` is stored as `NUMERIC(10,3)`, i.e. with
sub-cent precision, by design (the schema comment says this is intentional).
The backend summed this in the database correctly, but then cast the result
straight to a Python float with no explicit rounding rule before returning
it to the frontend.

**Root cause:** A plain `float()` cast plus Python's default `round()` does
not reliably round monetary values on a half-cent boundary, because the
binary floating point representation of the value is not exact. This does
not misbehave for every value, only specific ones landing on these binary
edge cases, which is exactly why it looked "intermittent" and hard to pin
down.

**Fix:** `calculate_total_revenue` and `calculate_monthly_revenue` now
quantize the summed total to the nearest cent using `Decimal` with
`ROUND_HALF_UP`, once, right after the database sum, before it is ever cast
to a float.

**Verified:** Manually inserted a temporary reservation that pushed a
property's total onto a half-cent boundary (`6100.505`). Before the fix, a
plain float cast plus `round()` would produce `6100.50`. After the fix, the
API correctly returns `6100.51`. This was a constructed test case built to
force the boundary condition, since the original seed data happens to sum to
clean values; it is not a claim that this exact scenario was present in the
provided data, only that the underlying rounding logic was unsafe.

## Bug 4: Monthly revenue used naive UTC month boundaries

**Symptom (Client A):** "We're showing different totals for March... worried
about accuracy for our board meeting."

**How found:** `calculate_monthly_revenue` was an unfinished placeholder that
always returned zero. Properties are stored with a `timezone` column
(Paris, New York), and reservations store `check_in_date` as a timestamp
with timezone. The seed data includes a reservation at `2024-02-29 23:30:00
UTC` for a Paris property; in Paris local time that is already `2024-03-01
00:30`.

**Root cause:** Bucketing "which month a reservation belongs to" by naive UTC
boundaries instead of the property's own local timezone will misclassify any
reservation near a month boundary, in either direction depending on the
property's timezone offset.

**Fix:** Finished `calculate_monthly_revenue` to look up the property's
timezone and build the start/end of the month as timezone-aware datetimes in
that local timezone before querying. Wired it into the existing dashboard
endpoint as optional `month`/`year` query parameters (calls without them
behave exactly as before).

**Verified directly against the database:**
- Naive UTC boundary for February 2024: incorrectly includes the boundary
  reservation (1 reservation, $1,250.00).
- Property-local (Paris) boundary for February 2024: correctly excludes it
  (0 reservations, $0.00).
- March 2024 via the fixed API: correctly includes all 4 reservations for
  the property, matching the all-time total exactly ($2,250.00).

## Bug 5: Property dropdown exposed other tenants' property names

**Symptom:** Found while browser-testing the fixes above, not originally
reported by a client, but the same category of issue Client B raised.

**How found:** After logging in as Client A, the property selector dropdown
listed all 5 properties across both tenants, including two that belong to
Client B (Lakeside Cottage, Urban Loft Modern).

**Root cause:** `frontend/src/components/Dashboard.tsx` had a hardcoded,
static list of all 5 properties, not scoped to the logged-in user's tenant.
Revenue figures themselves were not affected (the backend query is already
tenant-scoped), but property names from another company were still visible.

**Fix:** Added `GET /api/v1/properties`, scoped to the current user's
tenant, and replaced the hardcoded list in `Dashboard.tsx` with a fetch from
it on load.

**Verified:** Logged in as both clients in the browser. Client A's dropdown
now shows only their 3 properties; Client B's dropdown shows only their 3
properties, each with correct names.

## How to verify all of this yourself

```bash
docker-compose up --build
```

Log in as each client (see ASSIGNMENT.md for credentials) at
`http://localhost:3000` (or via `POST /api/v1/auth/login`), and:

- Compare the same property id across both accounts, refreshing repeatedly
  (Bug 2).
- Query `/api/v1/dashboard/summary?property_id=prop-001&month=3&year=2024`
  vs `month=2` for Client A (Bug 4).
- Check the property dropdown only shows properties for the logged in
  tenant (Bug 5).
