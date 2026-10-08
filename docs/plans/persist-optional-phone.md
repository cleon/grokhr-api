# Persist optional phone on employees

API work for the optional phone field once the shared Employee contract defines it.

## Steps

1. **Schema** — Add a nullable `phone` column on `employees` in `sql/schema.sql`.
2. **Read/write path** — Include `phone` in select and update column lists in `app/db.py`.
3. **Shared types** — Keep vendored `grokhr_shared.py` aligned with the shared package Employee shape that includes optional phone.
4. **Roster reads** — Return phone on the active roster / list responses the web directory uses.

## Out of scope

- Directory UI column (owned by grokhr-web)
- Backfilling invented phone numbers into `sql/seed.sql`
- Phone format validation beyond storing a string
