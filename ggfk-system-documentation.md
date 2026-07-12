# GGFK System Documentation

## Grading and School Domain Rules

- GGFK uses three canonical terms per school year: `1er Trimestre`, `2ème Trimestre`, and `3ème Trimestre`. All new term-bearing writes use these exact values; `backend/scripts/count_legacy_terms.py` is the read-only audit for legacy labels.
- Numeric course grades are normalized to `/20` and map to the nine-letter scale `A+ / A / B+ / B / C+ / C / D / E / F`. Conduct and work habits use letter assessments separately and never enter numeric course calculations.
- French-track Collège courses use the Benin Ministry notation-béninoise chain: `Moy_Int = mean(Interros)`, `MCC = mean(Moy_Int, Devoir)`, and trimester `Moy = mean(MCC, Composition)`. Only Interro, Devoir, and Composition items are valid in this mode.
- The bilingual bulletin carries distinct French, English, and bilingual averages. Bilingual is the equal mean of the French and English track averages and remains unavailable until both tracks have a value.
- GGFK's locked class taxonomy covers Nursery (`maternelle`), Primary (`primaire`), and Collège, with French/JSS dual names in Collège and C/D streams for `1ère` and `Terminale`.
- Parents may inspect individual scores during a trimester, but running averages and rankings are visible only in approved or sent bulletin snapshots.

### Course Coefficients

- Overall and language-track averages coefficient-weight courses when an admin configures coefficients on the course. A coefficient of `1` means ordinary equal weight, and all current courses use `1`.
- `backend/ggfk_coefficients.json` is intentional reference data for admins configuring upper classes (`4ème` through `Terminale`); it is not auto-loaded because course setup remains an explicit admin decision.
- Coefficients affect calculations but are not printed on the bulletin. This matches the school's official bulletin format; do not add a `Coef` column to the PDF.

## Authentication and Publication Boundaries

- JWTs are version-bound: password changes/resets and profile trash events invalidate older sessions. Forced first-login password changes are enforced by the backend, not only by frontend redirects.
- Parents see individual scores during the trimester, without live averages. Averages and rankings are published only through approved or sent bulletin snapshots.
- Bulletin state follows `draft -> approved -> sent`; edits to approved/sent conduct, work habits, or comments persist `needs_review`. Recovery is regenerate to draft, then approve and send again. Regeneration preserves human-entered details.
- A bulletin is an official snapshot and does not silently recompute after grade changes. Stale approve/send attempts require an explicit admin override.
- `ai_summary` is screen-only and never appears in the official PDF or invalidates bulletin status.

## Delivery and Audit

- Resend is the email delivery path. A `resend.dev` sender reaches only the Resend account owner; production parent delivery requires verified school-domain DNS and environment configuration, with no code rewrite.
- Generated temporary passwords are delivered in plaintext because they are short-lived forced-change credentials. They are never written to audit payloads.
- Grade notifications name the student and course but include no scores or averages. Bulletin notifications link parents to the authenticated approved/sent snapshot.
- SMS/WhatsApp production provider selection remains pending; Africa's Talking is planned. The current Twilio adapter is optional infrastructure, not the final provider commitment.
- Audit logs default to Operational events so authentication volume does not obscure school actions; Authentication and All filters retain access to every event. Anonymous failed-login/reset events intentionally have no actor.

## Local Unpushed Work

### A1.13b — Student Soft-Delete + Restore

- Added `students.deleted_at` and changed student delete to move students to Trash.
- Added admin restore and deleted-student listing.
- Normal admin, teacher, parent, report, roster, grade, and course-result workflows hide deleted students while preserving academic history.

### A1.13c — Admin Cleanup Delete Controls

- Added guarded admin cleanup controls for parents, teachers, courses, grade items, and enrollments.
- Parent delete is blocked while linked to active students.
- Teacher delete is blocked while courses or submitted grades are linked.
- Course delete is blocked when roster, grade item, grade, course result, or report snapshot data exists.
- Grade item delete is blocked when submitted grades exist.
- Normal cleanup actions move recoverable setup/academic records to Trash instead of permanently deleting them.
- Enrollment removal is audited and now soft-deletes the enrollment link.
- Frontend admin cleanup controls were added for parents, teachers, course detail unenrollment, safe course delete, and safe grade item delete.

### A1.13c.1 — Recoverable Owner Cleanup

- Added an admin-only cleanup tool at `/admin/danger-zone` (UI label: Nettoyage).
- Nettoyage uses a searchable record picker for students, parents, teachers, classes, courses, grade items, and reports; owners do not need to paste raw UUIDs.
- Nettoyage previews dependency counts before cleanup and requires typed confirmation.
- Confirmed cleanup creates a deletion batch, moves the target and dependencies to Trash, and stores `deleted_at` plus `deleted_batch_id`.
- Added `/admin/trash` to list deletion batches and restore an entire batch.
- Nettoyage itself never hard-deletes academic data; it creates recoverable batches. Explicit permanent purge exists only from Corbeille after a separate confirmation, while AuditLog remains permanent history.
- In production, the cleanup tool is blocked unless `ENABLE_DANGER_ZONE=true`.

### A1.13c.2 — Unified Corbeille + Purge Controls

- Unified `/admin/trash` so Corbeille lists deletion batches plus unbatched soft-deleted records such as students.
- Student deleted view is now a filtered Corbeille view, sharing the same restore path.
- Added permanent purge controls for individual Corbeille rows and emptying the Corbeille, with audit logs and counts.
- Added lazy 30-day auto-purge based on `deleted_at`; restore clears `deleted_at`, so re-deleted records receive a fresh retention window.
- Lazy purge runs when Corbeille is accessed because the app has no persistent scheduler; `deleted_at` indexes keep the retention sweep cheap.
- Added restore-order checks for unbatched child records: children cannot be restored while their parent entity remains deleted.
- Purge runs child-first inside a transaction/savepoint per entry and is permanently unrecoverable.
- Converted subjects/matières from guarded hard delete to guarded soft delete so they can appear in Corbeille.
- Added an Alembic migration for subject trash columns and missing `deleted_at` indexes; Isaac reviews and runs it locally/prod during deploy.

These changes are local only and are not marked as shipped to production.
