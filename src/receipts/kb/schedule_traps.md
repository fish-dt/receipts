# Schedule Trap Catalog (synthetic policy, original text)
## ST-1 DST gap and overlap
Local-time schedules between 01:00 and 03:59 are unsafe on daylight-saving change days: one night a time is skipped, another it runs twice. Prefer UTC. If local time is required, document the intended behavior for both days.
## ST-2 Overlapping runs
If a job can run longer than its interval, two copies may run at once. Require a concurrency limit or a lock, and state the maximum runtime.
## ST-3 Missing idempotency
A job that appends, charges, or sends must be safe to run twice. If idempotency is not evident in the source, mark the step unknown. Never assume.
## ST-4 File-drop triggers
Scripts that poll for a sentinel file depend on a shared directory. Flag as hidden coupling; an event-based trigger needs a human-chosen replacement.
## ST-5 Exit-code semantics
Patterns like `|| true` or a trailing `exit 0` hide failures. The migrated job must preserve the observable exit behavior, or the difference must be raised to a human. Never silently "fix" it.
## ST-6 Environment coupling
Values read from environment variables or shared mounts are inputs. List each one; do not invent values.
