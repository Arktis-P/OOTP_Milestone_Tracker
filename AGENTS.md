# Claude subagent delegation

- The primary `gpt-5.6-sol` agent owns decomposition, interface decisions, integration, and final verification.
- Use `sonnet5_worker` for bounded implementation, refactoring, and test tasks where speed and cost matter.
- Use `opus_worker` for difficult implementation, architecture-sensitive changes, deep debugging, and high-confidence review.
- Both Claude workers are authorized to inspect and modify this repository and to run the tests, builds, and local commands needed to complete their assigned scope.
- Give each worker explicit file ownership, acceptance criteria, relevant commands, and required verification. Workers must preserve unrelated user changes and must not revert other agents' edits.
- Avoid concurrent writes to the same files. The primary agent must inspect worker changes and run integration-level checks before reporting completion.
- Do not authorize commits, pushes, pull requests, destructive operations, or external-system mutations unless the user explicitly requests them.
- If a named Claude worker is unavailable in the current task, use a `gpt-5.6-terra` bridge to invoke `C:\Users\cwson\.local\bin\claude.exe -p` with the corresponding `--model sonnet` or `--model opus`, `--permission-mode acceptEdits`, and `--allowedTools Read,Edit,Write,Bash,Glob,Grep`. Never use `--dangerously-skip-permissions` or `bypassPermissions`.
