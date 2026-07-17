# MeterMesh

MeterMesh is a local, privacy-conscious usage dashboard for Codex, Claude Code, and OpenCode. It incrementally imports usage metadata into one app-owned SQLite index named **Unibase**, deduplicates overlapping live and backup sources, and serves Usage, Requests, and Data Health from committed SQL projections.

![MeterMesh 2.2.0 dashboard showing the All provider scope and Data Health](docs/screenshot-v2.2.0.png)

## Highlights

- Provider selector: All, Codex, Claude, OpenCode.
- Usage charts and provider-qualified model totals.
- Independent visualization ranges with daily, weekly, and monthly token buckets.
- Provider-aware Data Health with index integrity, coverage, and source freshness.
- Privacy-safe Requests with numbered pagination and grouping from 1 minute to 24 hours.
- Settings for source and model filtering, All-scope aggregation, reset, and Full reindex.
- Retained provenance: disabling one duplicate backup does not remove an event still supported by another source.
- Recorded OpenCode costs remain distinct from pricing estimates and unavailable costs.

## Unibase

The default database is:

```text
~/.metermesh/unibase.sqlite3
```

Override it with `METERMESH_UNIBASE_DB` or `--unibase-db`. Unibase is a rebuildable index. Provider files remain the source of truth and are opened read-only.

MeterMesh never resets or migrates `~/.codex/state_5.sqlite` or OpenCode's `opencode.db`. The old Claude `~/.claude/usage-dashboard.sqlite` is left untouched and is not used by MeterMesh 2.x.

## Data Sources

Defaults:

```text
Codex:    ~/.codex/sessions/**/rollout-*.jsonl
Claude:   ~/.claude/projects/**/*.jsonl
OpenCode: $XDG_DATA_HOME/opencode/opencode.db
          or ~/.local/share/opencode/opencode.db
```

For the live Codex source, MeterMesh also imports valid absolute rollout paths registered in `state_5.sqlite`. This automatically includes additional Codex profiles such as `~/.codex-work/sessions` without storing their raw paths in Unibase.

Compatibility overrides:

```text
CODEX_USAGE_DB / --db
CLAUDE_PROJECTS_DIR / --claude-projects
OPENCODE_USAGE_DB / --opencode-db
```

`--claude-db` remains accepted for one transition release but does not select the Unibase path.

## Backup Snapshots

MeterMesh creates an `add_stat` directory for every provider:

```text
~/.codex/add_stat/
~/.claude/add_stat/
<opencode-data-dir>/add_stat/
```

Recommended immutable snapshot layout:

```text
20260701T120000Z--before-reset--8f31a2c4/
├── snapshot.json
└── root/
```

Example manifest:

```json
{
  "format": "metermesh-provider-snapshot",
  "version": 1,
  "id": "stable-snapshot-id",
  "provider": "codex",
  "created_at": "2026-07-01T12:00:00Z",
  "label": "Before reset",
  "root": "root"
}
```

Legacy full copies placed directly under `add_stat` are detected only at fixed safe roots. New backups are registered unchecked. Legacy copies require two stable inventory observations before import.

## Privacy

Unibase stores usage metadata, hashed stream/event identities, token components, model/provider identifiers, cost semantics, and source provenance. It does not store prompts, responses, tool output, cwd, attachments, project paths, session titles, credentials, auth tokens, or account identity.

Requests and Settings APIs omit raw provider IDs and absolute source paths. Source errors are sanitized.

## Run

Requirements: Node.js 20+ and Python 3.10+.

```bash
npm install
npm run dev:all
```

Open <http://127.0.0.1:8765>.

On macOS, `Start MeterMesh.command` starts both the Python API and Vite frontend.

Direct API server:

```bash
python3 dashboard_api.py --host 127.0.0.1 --port 8766
```

## Settings And Maintenance

- **Apply** persists source, model, and All-scope aggregation preferences with optimistic revision checking.
- **Reset Unibase** requires `RESET UNIBASE`, preserves settings and source registry, and blocks automatic indexing until Full reindex.
- **Full reindex** builds a staging Unibase from live sources and enabled backups, runs invariants and `PRAGMA integrity_check`, then atomically swaps the database.
- Usage, Requests, and Data Health continue reading the previous committed database while staging is built.

## API

```text
GET  /api/usage
GET  /data.json              compatibility alias
GET  /api/requests
GET  /api/settings
POST /api/settings
POST /api/unibase/reset
POST /api/unibase/reindex
GET  /api/unibase/status
```

The default provider scope is `all`. Explicit `provider=codex`, `provider=claude`, and `provider=opencode` links remain supported.

## Verification

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/*.test.mjs
npm run build
npm run check
```

`npm run check` uses configured local provider data. Unit tests use synthetic privacy-safe fixtures.

## License

MIT. See [LICENSE](LICENSE).
