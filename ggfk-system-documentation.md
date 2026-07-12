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
- No permanent delete is added for academic data; AuditLog rows remain permanent history.
- In production, the cleanup tool is blocked unless `ENABLE_DANGER_ZONE=true`.

### A1.13c.2 — Unified Corbeille + Purge Controls

- Unified `/admin/trash` so Corbeille lists deletion batches plus unbatched soft-deleted records such as students.
- Student deleted view is now a filtered Corbeille view, sharing the same restore path.
- Added permanent purge controls for individual Corbeille rows and emptying the Corbeille, with audit logs and counts.
- Added lazy 30-day auto-purge based on `deleted_at`; restore clears `deleted_at`, so re-deleted records receive a fresh retention window.
- Added restore-order checks for unbatched child records: children cannot be restored while their parent entity remains deleted.
- Converted subjects/matières from guarded hard delete to guarded soft delete so they can appear in Corbeille.
- Added an Alembic migration for subject trash columns and missing `deleted_at` indexes; Isaac reviews and runs it locally/prod during deploy.

These changes are local only and are not marked as shipped to production.
