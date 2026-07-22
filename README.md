# Property Revenue Dashboard: Debugging Challenge

## Video walkthrough

[Loom video](https://www.loom.com/share/98aa40fb56e84a9a967ba1ed258c5822)

## What this is

This branch investigates and fixes the issues reported in `ASSIGNMENT.md`:
Client A seeing incorrect March revenue totals, Client B seeing revenue
numbers that looked like they belonged to another company, and the finance
team noticing totals that were slightly off by a few cents.

See `FINDINGS.md` for the full write-up of each bug: symptom, how it was
found, root cause, the fix, and how it was verified.

## Running it

```bash
docker-compose up --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs

Client credentials are in `ASSIGNMENT.md`.
