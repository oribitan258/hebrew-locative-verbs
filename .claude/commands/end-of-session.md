---
description: (Ori, Efrat) Close this session's stage: checks, persistent docs, then CONTINUE / SEND TO PARTNER / WAIT
---

Follow `docs/STAGES.md` §2 exactly.

1. Identify the person (`uv run python -m hebloc whoami`) and the stage done in this session (STAGES.md §3 for Ori,
   §4 for Efrat).
2. Run that stage's completion checks. If one fails, say so: the stage is not done.
3. Update the persistent record:
   - **Ori:** the "Current position" line and the `Status` / "Partner status" cells of STAGES.md, the
     "Current position" block of `docs/HANDOFF.md`, the CLAUDE.md scope line and the `docs/roadmap.md` §5/§6 rows when
     they change, `docs/decisions.md` only if a decision was taken, and the memory. Show the diff. Commit and push
     only if Ori approves in this session.
   - **Efrat:** `data/outbox/efrat-s6/STATE.md` only (format: STAGES.md §7). Never commit or push.
4. Print exactly one result, with exact instructions:
   - **CONTINUE**: "Next session: `start` → stage `<id>`."
   - **SEND TO PARTNER**: the folder, the channel (Google Drive, OneDrive or USB; never git), the message (STAGES.md
     §8), then what to do next.
   - **WAIT**: for what, from whom, and what `start` will check.
