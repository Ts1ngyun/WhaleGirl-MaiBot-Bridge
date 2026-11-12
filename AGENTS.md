# Instructions for installation and maintenance agents

Read README.md, docs/INSTALL.md, docs/MAINTENANCE.md and docs/RELEASE-CHANGES.md before changing or deploying this project. This repository may lag upstream; do not treat recorded compatibility as a promise for future releases.

## Non-negotiable boundaries

- Never commit or upload keys, tokens, account/chat identifiers, real conversations, personal absolute paths, user configuration, logs, backups, databases, models or binaries. Do not echo credential values. Inspect staged files, not only `.gitignore`.
- Do not modify WhaleGirl or MaiBot official remotes. Do not fork or push complete upstream trees as part of bridge maintenance. Preserve upstream notices and AGPL obligations for distributed modified WhaleGirl files.
- Default model execution belongs to MaiBot. Never copy WhaleGirl API keys, persona or task settings automatically. Voice synthesis API remains configured in WhaleGirl. Do not reintroduce local RVC.
- Preserve lowercase `/v` authorization, cancellation, deduplication, no automatic retry of uncertain sends, allowed-chat checks, verified account/window targeting, attachment draft quarantine, and remote Key authentication.
- Do not send live WeChat messages or voice for tests without explicit target/content authorization. Prefer isolated fixtures and preview chats prefixed `__test__` (local test server only).
- Do not overwrite a running/user-modified installation. First identify paths/versions and existing bridge association, read upstream instructions, stop processes using the documented method, make backups, review the file replacement plan. Install is preview-only unless `--apply` is supplied.

## Expected update procedure

1. Inspect Git status; preserve user changes. Read source provenance and record the new upstream versions and exact commits when available.
2. Compare each modified upstream file by semantic change listed in docs/MAINTENANCE.md. Port those small hooks onto the new upstream version; never copy our old full files blindly over a new release.
3. Keep adapter SDK operations in the plugin. Obtain user authorization before changing MaiBot core; normally no core modification is needed.
4. Make compatibility validation match genuinely tested versions. Do not widen manifest or installer gates merely to silence a mismatch.
5. Run syntax checks and isolated tests; add regression coverage for changed contracts. Windows microphone/GUI checks require a local interactive environment. No live-send test by default.
6. Run privacy checks, inspect every staged filename and textual diff, verify only the intended repository remote is set. Stop and report any unknown sensitive content. Never force-push to resolve remote history.
7. Update human installation guide, changelog, dependency list, provenance and known limits. State what was tested and what still requires user reconnection/manual validation.

## Quick commands

```powershell
python -m unittest test_relay test_remote test_emoji test_distribution
python scripts/privacy_check.py
git diff --check
git diff --cached --stat
git remote -v
```

Tests create temporary databases and synthetic messages, not real user data. Never run `install.py --apply` against the developer's live installation merely to test the installer; use a temporary fixture. Installation backups and association files are private local artifacts.
