# GGFK System Documentation

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

- Added an admin-only Owner Danger Zone at `/admin/danger-zone`.
- Danger Zone uses a searchable record picker for students, parents, teachers, classes, courses, grade items, and reports; owners do not need to paste raw UUIDs.
- Danger Zone previews dependency counts before cleanup and requires typed confirmation.
- Confirmed cleanup creates a deletion batch, moves the target and dependencies to Trash, and stores `deleted_at` plus `deleted_batch_id`.
- Added `/admin/trash` to list deletion batches and restore an entire batch.
- No permanent delete is added for academic data; AuditLog rows remain permanent history.
- In production, Danger Zone is blocked unless `ENABLE_DANGER_ZONE=true`.

These changes are local only and are not marked as shipped to production.
