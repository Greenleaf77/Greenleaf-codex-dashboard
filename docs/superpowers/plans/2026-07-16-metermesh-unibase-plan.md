# План MeterMesh: Unibase, Codex, Claude, OpenCode, All, Requests и Settings

## Статусы выполнения

Исполняемый чек-лист находится в разделе 13 и обновляется по ходу реализации:

- `[ ]` — не начато;
- `[*]` — выполняется сейчас;
- `[X]` — реализовано/завершено и проверено указанными тестами или review;
- `[!]` — заблокировано, рядом обязательно указана причина;
- `[-]` — осознанно исключено из scope с объяснением.

Одновременно только один крупный этап может иметь статус `[*]`. Пункт нельзя отмечать `[X]`, пока не выполнена относящаяся к нему проверка. Требования в разделах 1–12 являются спецификацией, а раздел 13 — единственным трекером выполнения.

## Context

Проект переименовывается в **MeterMesh**. Codex, Claude и OpenCode остаются названиями провайдеров, а архитектура перестаёт быть привязана к ним: новые провайдеры должны подключаться через общий source/adapter contract.

Текущий Codex-путь повторно читает сотни мегабайт rollout JSONL и создаёт сотни тысяч Python-объектов при загрузке. Одновременно пользователь хранит несколько полных резервных копий `.codex`, `.claude` и OpenCode data directory, которые могут полностью совпадать, быть более новыми supersets или частично расходиться. Простое сканирование всех папок приведёт к двойному учёту и небезопасному удалению событий при отключении одного источника.

Цель — сделать одну app-owned базу **Unibase**, инкрементально загружать в неё live-данные и включённые backup snapshots, глобально устранять дубли с сохранением provenance, строить Usage/Diagnostics/Requests только по Unibase и добавить Settings для управления источниками и обслуживанием базы.

Согласованное UI-поведение сохраняется:

- вкладки `Usage / Diagnostics / Requests`;
- первый пункт provider selector — `All`, затем `Codex`, `Claude`, `OpenCode`;
- при отсутствующем или невалидном `provider` используется `all`; явные старые `provider=codex|claude` URL продолжают работать;
- `All` объединяет активные события всех провайдеров для Usage, Diagnostics и Requests без повторного учёта пересекающихся source copies внутри каждого провайдера;
- Requests работает для `All`, Codex, Claude и OpenCode;
- пагинация `Previous / Next` с номером страницы;
- группировки `None`, `1m`, `15m`, `30m`, `1h`, `6h`, `12h`, `24h`;
- page size считает события без группировки и главные ветки с группировкой;
- в Requests не показываются session/response/event IDs, пути, промпты, ответы, tool content или cwd;
- exact, cumulative fallback, Claude metadata и OpenCode recorded usage имеют честные разные labels и не выдаются за подтверждение billing/acceptance.

---

## 1. Product naming и расположение Unibase

- Product: **MeterMesh**.
- Unified app-owned database: **Unibase**.
- Default path: `~/.metermesh/unibase.sqlite3`.
- Environment override: `METERMESH_UNIBASE_DB`.
- CLI override: `--unibase-db`.
- Unibase является пересоздаваемым индексом; provider files остаются source of truth.
- `~/.codex/state_5.sqlite` всегда открывается read-only и никогда не сбрасывается/изменяется MeterMesh.
- OpenCode data dir: `$XDG_DATA_HOME/opencode`, если `XDG_DATA_HOME` задан, иначе `~/.local/share/opencode`.
- `<opencode-data-dir>/opencode.db` всегда открывается read-only с `query_only=ON` и никогда не мигрируется/сбрасывается/изменяется MeterMesh.

Создать provider-neutral core:

- [unibase.py](unibase.py) — schema, migrations, settings, source registry, provenance, active projection, операции reset/reindex и SQL queries;
- [codex_usage.py](codex_usage.py) — Codex discovery, rollout consolidation и telemetry reconstruction;
- [claude_usage.py](claude_usage.py) — Claude adapter без собственной отдельной usage-базы;
- [opencode_usage.py](opencode_usage.py) — read-only OpenCode SQLite adapter, schema capability detection, incremental message import и backup dedup;
- [dashboard_api.py](dashboard_api.py) — HTTP, validation, pricing, response shaping и legacy HTML; production GET-path больше не сканирует JSONL напрямую.

SQLite:

- WAL, foreign keys, busy timeout;
- `PRAGMA user_version` и миграции внутри `BEGIN IMMEDIATE`;
- отдельные parser versions по provider;
- provider/source operation locks для ThreadingHTTPServer.

---

## 2. Структура backup snapshots в `add_stat`

MeterMesh при первом запуске создаёт:

```text
~/.codex/add_stat/
~/.claude/add_stat/
<opencode-data-dir>/add_stat/
```

### Нормализованный рекомендуемый формат

Каждая подпапка — один immutable snapshot:

```text
<YYYYMMDDTHHMMSSZ>--<human-slug>--<short-id>/
├── snapshot.json
└── root/
```

Codex:

```text
~/.codex/add_stat/
└── 20260701T120000Z--before-reset--8f31a2c4/
    ├── snapshot.json
    └── root/
        ├── sessions/YYYY/MM/DD/rollout-*.jsonl
        ├── state_5.sqlite          # optional metadata
        └── session_index.jsonl     # optional metadata
```

Claude:

```text
~/.claude/add_stat/
└── 20260701T120000Z--old-machine--db20af71/
    ├── snapshot.json
    └── root/
        └── projects/<opaque-project-key>/**/*.jsonl
```

OpenCode:

```text
<opencode-data-dir>/add_stat/
└── 20260701T120000Z--before-upgrade--51ae607d/
    ├── snapshot.json
    └── root/
        └── opencode.db
```

Нормализованный OpenCode snapshot содержит standalone transactionally consistent `opencode.db`, созданный SQLite backup API, а не произвольным копированием live-файла во время записи. `-wal`/`-shm` не требуются для normalized snapshot.

`snapshot.json`:

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

Manifest пишется последним и является readiness marker. Проверять provider/version, безопасный relative root и path traversal. Нормализованную папку без валидного manifest считать incomplete и не импортировать.
Допустимые manifest providers в этом релизе: `codex`, `claude`, `opencode`.

### Поддержка уже существующих полных копий

Пользователь может просто положить старую копию целиком как прямого ребёнка `add_stat`, без ручной перестройки:

```text
~/.codex/add_stat/my-old-backup/.codex/...
~/.codex/add_stat/my-old-backup/sessions/...
~/.claude/add_stat/laptop-copy/.claude/projects/...
~/.claude/add_stat/laptop-copy/projects/...
~/.local/share/opencode/add_stat/laptop-copy/opencode.db
~/.local/share/opencode/add_stat/laptop-copy/opencode/opencode.db
~/.local/share/opencode/add_stat/laptop-copy/.local/share/opencode/opencode.db
```

Для direct child без manifest выполнить shallow detection только по:

- `<child>`;
- `<child>/.codex` для Codex;
- `<child>/.claude` для Claude.
- `<child>/opencode` и фиксированный `<child>/.local/share/opencode` для OpenCode.

Не выполнять произвольный recursive root search. Если найдено несколько равнозначных provider roots с usage payload, источник помечается `ambiguous` и не включается автоматически.

Legacy source считается готовым только после двух одинаковых inventory checks подряд: eligible relative paths, sizes и mtimes. Это защищает от индексации папки во время копирования.

Статус таких источников в Settings: `Legacy layout`. Новые найденные backup sources по умолчанию выключены.

### Разрешённые usage-файлы

Codex required:

```text
sessions/**/rollout-*.jsonl
```

Codex optional metadata:

```text
state_5.sqlite
state_5.sqlite-wal
state_5.sqlite-shm
session_index.jsonl
```

Не импортировать для usage: auth/config, logs/goals/memories DB, attachments, cache, plugins, skills, shell snapshots.

Claude required:

```text
projects/**/*.jsonl
```

Включая primary transcripts и `subagents/*.jsonl`. Исключить history, sessions process files, `.claude.json.backup.*`, tool-results, file-history, meta files и старый `usage-dashboard.sqlite`.

OpenCode required:

```text
opencode.db
```

OpenCode optional legacy consistency files:

```text
opencode.db-wal
opencode.db-shm
```

Normalized snapshots обязаны содержать standalone consistent DB. Legacy raw copies с WAL импортируются только после stable inventory и успешного read-only consistency check; при необходимости MeterMesh собирает private app-owned staging copy и никогда не пишет в source directory. Читать разрешено только usage-relevant `message`/`session` schema metadata и assistant usage columns/JSON fields. Никогда не читать и не переносить `account`, `control_account`, `credential`, auth tokens, prompt text, parts/tool output, project paths, session titles или другие content-bearing поля.

---

## 3. Unibase source registry и настройки

### `app_settings`

Singleton row:

- settings revision;
- `ignore_codex_auto_review`;
- legacy cookie/URL migration marker;
- timestamps.

Настройки живут в Unibase, но **Reset Unibase их сохраняет**.

### `sources`

Каждый live или backup source получает стабильный `source_id`:

- provider;
- `kind = live | normalized_backup | legacy_backup`;
- internal root path;
- safe display label и relative backup directory name;
- enabled;
- priority;
- snapshot ID/date;
- discovery status: ready/incomplete/ambiguous/unavailable/error/not_indexed;
- stale flag;
- last successful scan generation, counts и sanitized error.

Live Codex, Claude и OpenCode sources регистрируются автоматически и всегда активны в первой версии. Settings checkboxes управляют только backups.

Default conflict priority:

1. live — 1000;
2. normalized backup — 500;
3. legacy backup — 400;
4. при равном приоритете newer snapshot date, затем stable source ID.

Priority применяется только для реально конфликтующих payload variants. Non-conflicting records разных sources объединяются.

### Enabled semantics

- Checked backup участвует в active totals и индексируется/обновляется.
- Newly discovered unchecked backup регистрируется, но его содержимое не парсится до включения.
- Если ранее индексированный backup выключен, его occurrences сохраняются, но перестают поддерживать active events.
- Повторное включение неизменённого источника восстанавливает данные без полного reparsing; затем запускается incremental validation.
- Purge/delete source data не входит в первый релиз.

---

## 4. Canonical data + provenance вместо владения событием одним файлом

Нельзя хранить canonical event с единственным `source_path`: отключение одного дубля не должно удалить событие, которое остаётся в другом source.

### Основные таблицы

#### `source_files`

- `(source_id, relative_path)` unique;
- file kind, size, mtime, generation;
- complete-line offset;
- content hash;
- scan generation seen;
- parser checkpoint для append-only live files.
- для SQLite sources — schema fingerprint, transaction snapshot marker и provider-specific change cursor вместо byte offset.

#### `content_blobs`

- SHA-256 + size unique;
- позволяет не парсить повторно byte-identical rollout/transcript copies;
- особенно важно для последовательных backup supersets.

#### `logical_streams`

- provider-neutral logical transcript/rollout identity;
- provider;
- hashed session/stream key;
- model metadata;
- consolidation/conflict status.

#### `record_variants`

Минимальные metadata-only records, нужные для reconstruction:

- logical record key;
- type;
- timestamp/sequence;
- usage components;
- marker flags;
- normalized hash.

Не хранить prompt/response/tool/attachment/cwd content.

#### `record_occurrences`

Many-to-one provenance: record variant ↔ source file/source/offset/generation.

#### `event_variants`

Нормализованные usage candidates:

- provider event key;
- timestamp/model и provider-native model/provider identifiers без account identity;
- exact/derived/metadata semantics;
- token components: input, cache read, cache write, output, reasoning;
- recorded/estimated cost value и честная cost semantics;
- classification;
- normalized payload hash.

#### `event_occurrences`

Many-to-one evidence: event variant поддерживается одним или несколькими sources/files.

#### `canonical_events`

Provider-global event identity, candidate variants и conflict state.

#### `active_events`

Материализованная query projection:

- только события, поддержанные хотя бы одним активным source;
- selected candidate по deterministic rules;
- current Unibase generation;
- indexes по provider/time, provider/model/time и logical stream.

Source checkbox changes перестраивают `active_events` транзакционно и не требуют чтения файлов.

#### `diagnostic_events` / `operations`

- compact Codex telemetry diagnostics;
- source/consolidation counters;
- reset/reindex operation state/progress.

---

## 5. Инкрементальный scan и reconciliation

- Полный inventory источника собирается до удаления missing occurrences.
- Append-only live JSONL читаются с последнего complete-line offset.
- Partial final line не коммитится до завершения.
- Replaced/truncated file получает новую generation и reparsing.
- Missing file reconciliation выполняется только после успешного полного source scan.
- Source unavailable или scan failure не означает «пустой source»: сохранить last successful occurrences, пометить stale/error.
- Enabled stale source продолжает давать last committed data; пользователь может выключить его в Settings.
- Backup content hashes позволяют reused parse для идентичных файлов.
- После bootstrap обычные GET-запросы возвращают последнюю committed generation и не ждут full filesystem scan.
- Startup и explicit refresh планируют debounced incremental scan live + enabled backups.

---

## 6. Provider-specific deduplication и режим All

### Claude

Global event key:

1. `provider + uuid`;
2. fallback `provider + message.id`;
3. fallback source-independent normalized metadata hash.

Fallback hash включает timestamp, model, hashed session key и usage components, но не source path/offset и не message content.

- Same key + same payload → один variant, несколько occurrences.
- Same key + different payload → conflict variants; selected variant определяется source priority.
- Project directory names остаются opaque.
- Subagent usage не отбрасывается.

### Codex

`state_5.sqlite` используется только для metadata enrichment. Старые absolute `threads.rollout_path` не доверять: backup rollouts искать напрямую в `sessions/**/rollout-*.jsonl`.

Logical rollout identity:

1. `session_meta.payload.id`;
2. fallback UUID из rollout filename с поддержкой `/` и `\`;
3. final source-independent metadata fingerprint с diagnostic warning.

Не использовать parent `session_id` как primary identity: Codex subagents должны оставаться отдельными logical streams.

Перед cumulative reconstruction объединить все активные copies одного logical rollout:

1. Byte-identical files → один content blob + несколько occurrences.
2. Strict-prefix copy → provenance сохраняется, active sequence берётся из более полного superset.
3. Divergent copies:
   - align по intrinsic IDs;
   - иначе type + timestamp + metadata-only normalized identity + duplicate ordinal;
   - non-conflicting additions объединяются;
   - conflicting payloads сохраняются как variants и выбираются по source priority;
   - conflict показывается в diagnostics.

Только после consolidation выполнить existing telemetry algorithm:

- exact `raw_response_completed` по hashed response ID, если доступен;
- cumulative token_count baseline/replay/update/reset/unverifiable;
- exact suppresses covered cumulative snapshot;
- source-independent fallback event key строится из logical stream + canonical record identity;
- date filters применяются после reconstruction.

При смене backup checkbox пересчитываются только affected logical streams из stored record variants, без reread JSONL.

### OpenCode

Live source по умолчанию: `<opencode-data-dir>/opencode.db`; overrides: `OPENCODE_USAGE_DB` и `--opencode-db`.

Импорт выполняется внутри одной read-only SQLite transaction, чтобы `opencode.db` и активный WAL читались как согласованный snapshot. Adapter сначала проверяет schema capabilities и parser version. Неизвестная/несовместимая схема переводит source в `error`/`stale`, не удаляя последнюю успешную projection.

Usage event строится только из assistant rows таблицы `message`:

- canonical key: `opencode + message.id`;
- fallback при отсутствии стабильного ID: source-independent hash из hashed session key, timestamp, `providerID`, `modelID` и usage components;
- timestamp: `data.time.completed`, fallback `data.time.created`, затем column `time_updated`;
- model identity: `providerID + modelID`; account IDs/email/URL не читаются;
- tokens: `data.tokens.input`, `output`, `reasoning`, `cache.read`, `cache.write`;
- cost: `data.cost` с label `Recorded by OpenCode`, не billing confirmation; если поле отсутствует, допустим отдельный `Estimated` fallback через pricing catalog;
- rows без usage components не создают usage event;
- session-level `tokens_*`/`cost` используются только для integrity diagnostics и не суммируются поверх message events;
- `part.data`, prompts, responses, tools, paths, titles и credential/account tables не читаются.

Incremental live scan использует `message.time_updated + message.id` cursor, повторно читает overlap window для late updates и периодически выполняет ID-only reconciliation удалений. Backup DB импортируется как immutable content blob. Одинаковый `message.id` и payload в live/нескольких backups даёт один event variant с несколькими occurrences; конфликт payload выбирается по source priority и попадает в diagnostics.

### All

`provider=all` является query scope, а не отдельным source/provider в Unibase:

- объединяет `active_events` для `codex`, `claude`, `opencode`;
- canonical/event/session keys всегда provider-prefixed, поэтому одинаковые native IDs разных providers не склеиваются;
- distinct sessions считаются по `(provider, logical_stream)`;
- model grouping использует `(provider, native_provider_id, model)` и не смешивает одноимённые модели разных providers; UI показывает provider-qualified label;
- token totals суммируются по общей canonical schema, включая cache read/write;
- cost response содержит breakdown по `recorded`, `estimated` и `unavailable`; смешанная сумма не называется billing total;
- pagination snapshot фиксирует одну Unibase generation для всех providers.

---

## 7. SQL queries для Usage, Diagnostics и Requests

[dashboard_api.py](dashboard_api.py) переводится с raw Python event lists на SQL по `active_events`.

Usage сохраняет текущий payload contract:

- totals/distinct sessions;
- daily;
- models;
- model × day;
- chart buckets × model;
- pricing/current cost calculation;
- streaks и gap filling выполняются поверх небольших aggregate rows.
- provider breakdown и provider-qualified model keys для `all`.

`/data.json` остаётся compatibility alias для `/api/usage`.

Diagnostics становится provider-aware: Codex сохраняет telemetry reconstruction details, Claude и OpenCode показывают import/dedup/conflict/schema counters, а `All` — общий provider breakdown плюс Codex telemetry subsection. Source health для всех трёх providers также показывается в Settings.

Timestamp хранится в UTC. Frontend передаёт IANA timezone; backend использует `zoneinfo` для day/time buckets и корректных DST boundaries.

---

## 8. Requests API и UI

Добавить `GET /api/requests`.

Параметры:

- `provider=all|codex|claude|opencode`, range/start/end;
- timezone;
- legacy `ignore_auto_review` override;
- `group=none|1m|15m|30m|1h|6h|12h|24h`;
- `page`, 1-based;
- `page_size=10|25|50|100`, default 25;
- `snapshot` — high-water generation/event ID первой страницы.

Сохраняется ранее выбранная **номерная пагинация**, не cursor-only navigation.

Ungrouped:

- page size ограничивает события;
- stable order: timestamp DESC + internal key DESC.

Grouped:

1. Посчитать distinct buckets.
2. Выбрать page of bucket starts.
3. Агрегировать выбранные buckets.
4. Загрузить все children этих buckets.
5. Page size ограничивает только главные ветки.

Response: page/total pages/total top-level rows/has previous/has next/snapshot/items. Snapshot предотвращает сдвиг страниц во время append.

Видимые event fields:

- provider, а в `All` также provider-qualified model label;
- timestamp;
- model;
- input/output/reasoning;
- cache read/cache write отображаются раздельно, при этом compatibility `cached` остаётся alias для cache read;
- total without/with cache;
- exact/cumulative/Claude metadata/OpenCode recorded label;
- cost + `cost_kind=recorded|estimated|unavailable` без ложного billing claim.

Grouped tree использует `<details>/<summary>`; раскрытие не делает новый request.

---

## 9. Settings API

Расширить [dashboard_api.py](dashboard_api.py) поддержкой `do_POST`, JSON content-type/body-size validation и sanitized errors. [vite.config.mjs](vite.config.mjs) проксирует весь `/api`.

### `GET /api/settings`

Возвращает:

- settings revision;
- persisted auto-review preference;
- backups grouped by Codex/Claude/OpenCode;
- safe label, relative folder name, enabled, layout kind, snapshot date, indexed/not-indexed/stale/error/ambiguous status, counts и last successful scan;
- Unibase display path `~/.metermesh/unibase.sqlite3`, generation/state/counts/current operation.

Не отдавать absolute source paths.

### `POST /api/settings`

Body содержит revision, `ignore_codex_auto_review` и backup `{source_id, enabled}`. Strict validation, optimistic revision, `409` при stale draft.

Apply:

- сохраняет settings;
- выключенные sources удаляются из active projection, но не из retained provenance;
- newly enabled/not-indexed source ставится в background import;
- ранее индексированный enabled source активируется сразу и затем валидируется incrementally;
- frontend invalidates Usage/Diagnostics/Requests caches.

### `POST /api/unibase/reset`

Требует явный confirmation `RESET UNIBASE`.

- Не трогает `.codex`, `.claude`, OpenCode DB и backup folders.
- Сохраняет app settings, source registry, labels и checkbox states.
- Очищает derived files/checkpoints/records/events/diagnostics/active projection.
- Ставит sources в `not_indexed`.
- Состояние `reset_empty` блокирует автоматическую индексацию.
- UI показывает «Unibase was reset. Run Full reindex».

### `POST /api/unibase/reindex`

- Возвращает `202` + operation ID.
- Создаёт staging Unibase в `~/.metermesh/`.
- Копирует settings и stable source IDs.
- Полностью индексирует live sources + **только включённые backups**.
- Выполняет invariants и `PRAGMA integrity_check`.
- Пока build идёт, GET продолжает читать предыдущую committed Unibase.
- При успехе кратко берёт swap lock и atomically replaces main DB.
- При ошибке staging удаляется, текущая DB остаётся.
- Reset/settings/reindex mutations во время операции получают `409`.

Unchecked backups остаются в registry, но после полного reindex не имеют derived data до следующего включения.

### `GET /api/unibase/status`

Operation progress, generation, state и sanitized error для polling модального окна.

---

## 10. Settings modal и перенос auto-review

В header добавить Settings button с gear icon и `aria-haspopup="dialog"`. Текущий Ignore `codex-auto-review` checkbox полностью убрать из header.

Переиспользовать lifecycle native `<dialog>` из Custom Range, но выделить generic centered dialog helpers/styles.

Settings modal:

1. **Preferences**
   - Ignore `codex-auto-review` model.
2. **Backup sources**
   - отдельные Codex/Claude/OpenCode groups;
   - checkbox, label, snapshot date, relative folder, Normalized/Legacy, indexed/stale/error/ambiguous status.
3. **Unibase**
   - path/generation/indexed and active counts;
   - Full reindex;
   - danger-zone Reset Unibase.
4. **Actions**
   - Cancel / Apply.

Поведение:

- open создаёт local draft;
- Cancel ничего не меняет;
- Apply отправляет `POST /api/settings`;
- при dirty draft reset/reindex disabled до Apply/Cancel;
- Reset открывает второе destructive confirmation dialog с вводом `RESET UNIBASE`;
- Reindex показывает progress внутри Settings и блокирует повторные mutations;
- successful operation обновляет generation и все dashboard caches.

Auto-review persistence:

- explicit legacy URL param остаётся request override для старых links;
- существующий cookie один раз seed-ит server setting при миграции;
- новые URL больше не сериализуют preference постоянно;
- Apply обновляет server setting и compatibility cookie, затем удаляет legacy override из URL.

---

## 11. Полный MeterMesh branding

Обновить runtime/release identity, но не provider/domain strings.

Runtime:

- [src/main.js](src/main.js): стабильный MeterMesh header/neutral mesh mark; `All` использует neutral mesh mark, Codex/Claude/OpenCode logos остаются только provider selector; title `MeterMesh · All/Codex/Claude/OpenCode`; Settings button и MeterMesh error/loading copy.
- [index.html](index.html): `MeterMesh` title.
- [dashboard_api.py](dashboard_api.py): module/CLI/User-Agent/startup/legacy HTML/error pages → MeterMesh/Unibase.
- [dev.mjs](dev.mjs): startup/port/shutdown messages.

Package/release:

- [package.json](package.json) и [package-lock.json](package-lock.json): name `metermesh`, version `2.0.0`, description.
- Rename `Start Codex Usage Dashboard.command` → `Start MeterMesh.command`.
- [README.md](README.md): MeterMesh, Unibase architecture/path, add_stat convention, Settings, reset/reindex, Requests, privacy и new repo URL.
- [CHANGELOG.md](CHANGELOG.md): новый `2.0.0`, исторические provider entries сохраняются.
- [LICENSE](LICENSE): MeterMesh contributors.
- [.claude/skills/verify/SKILL.md](.claude/skills/verify/SKILL.md): MeterMesh/Unibase/Settings/Requests checks.
- Новый screenshot filename/alt text.

External release step после source rename: GitHub repository rename, local directory/remotes и README clone URLs. Не выполнять blind global `Codex -> MeterMesh`: сохранить `~/.codex`, provider=codex, model names, environment variables и telemetry documentation.

Brand visual direction:

- сохранить warm graphite dashboard system;
- MeterMesh mark — нейтральная сеть/mesh, не provider logo;
- chart series colors остаются стабильными по model identity;
- перед релизом прогнать categorical palette через dataviz validator в dark mode и проверить legend/table/accessibility.

---

## 12. Migration и backward compatibility

Первый запуск:

1. создать `~/.metermesh` и Unibase schema;
2. зарегистрировать live Codex/Claude/OpenCode sources;
3. создать `~/.codex/add_stat`, `~/.claude/add_stat` и `<opencode-data-dir>/add_stat`;
4. discover normalized/legacy backups;
5. новые backups оставить unchecked;
6. запустить initial background bootstrap live sources.

Старый `~/.claude/usage-dashboard.sqlite` оставить нетронутым и не импортировать: authoritative Claude JSONL пересобираются в Unibase.

Совместимость:

- сохранить `CODEX_USAGE_DB`, `--db`, `CLAUDE_PROJECTS_DIR`, `--claude-projects`; добавить `OPENCODE_USAGE_DB`, `--opencode-db`;
- сохранить `/data.json`;
- сохранить provider/range/chart/cache URL params;
- сохранить legacy ignore-auto-review URL/cookie override;
- `--claude-db` принять один переходный release с warning, но не использовать как Unibase path;
- production direct scanner удалить только после parity tests.

---

## 13. Исполняемый порядок реализации

Статусы ниже обновляются сразу при начале/завершении работы, а не задним числом.

### 13.0 Подготовка плана

- [X] Перевести план на статусы `[ ]`/`[*]`/`[X]`/`[!]`/`[-]` и единый исполняемый чек-лист.
- [X] Добавить согласованный scope OpenCode и `All`, проверив фактическую schema локальной `opencode.db`.

### 13.1 MeterMesh/Unibase foundation

- [X] Добавить Unibase path/env/CLI resolution, SQLite pragmas, migrations и operation locks.
- [X] Реализовать app settings, stable source registry, generations и sanitized operation state.
- [X] Реализовать normalized/legacy discovery для Codex, Claude и OpenCode `add_stat`.
- [X] Добавить read-only source guarantees и privacy allowlist для всех providers.
- [X] Покрыть foundation/discovery/migration tests и только после этого отметить этап завершённым.

### 13.2 Provenance и active projection

- [X] Создать `source_files`, `content_blobs`, `logical_streams`, record/event variants и occurrences.
- [X] Реализовать deterministic conflict selection и provider-prefixed canonical identities.
- [X] Реализовать transactional rebuild `active_events` при переключении sources.
- [X] Проверить disable/re-enable, stale source и source reconciliation без потери retained provenance.

### 13.3 Claude adapter

- [X] Перенести Claude ingestion в общий adapter contract без отдельной usage DB.
- [X] Реализовать UUID/message/fallback dedup across live/backups, subagents и conflicts.
- [X] Реализовать incremental offsets, partial lines, truncate/replace/delete reconciliation.
- [X] Подтвердить parity текущих Claude totals/requests тестами.

### 13.4 OpenCode adapter

- [X] Создать `opencode_usage.py` и schema capability detection для `opencode.db`.
- [X] Реализовать read-only WAL-consistent live transaction и immutable backup import.
- [X] Импортировать assistant message usage: provider/model, timestamps, input/output/reasoning/cache read/cache write и cost semantics.
- [X] Реализовать `message.id` dedup, fallback hash, conflict variants, incremental cursor и deletion reconciliation.
- [X] Доказать тестами отсутствие чтения/сохранения credentials, prompts, parts, paths, titles и account identity.
- [X] Сверить message sums с session aggregates только как integrity diagnostic, без двойного учёта.

### 13.5 Codex adapter

- [X] Вынести direct rollout discovery и metadata enrichment в `codex_usage.py`.
- [X] Реализовать identical/prefix/divergent consolidation до cumulative reconstruction.
- [X] Сохранить exact/fallback suppression, reset/replay/unverifiable semantics и subagent identities.
- [X] Подтвердить telemetry parity и multisource conflict behavior тестами.

### 13.6 SQL cutover и All

- [X] Перевести Usage/Charts/Models на SQL по `active_events`.
- [X] Добавить `provider=all` как default scope и provider breakdown.
- [X] Реализовать provider-qualified session/model identities и mixed cost breakdown.
- [X] Сделать Diagnostics provider-aware и удалить synchronous scans из production GET path.
- [X] Подтвердить, что `All` равен сумме трёх provider scopes без cross-provider collisions.

### 13.7 Requests API/UI

- [X] Реализовать `/api/requests` для All/Codex/Claude/OpenCode.
- [X] Реализовать numbered pagination, stable snapshot и все grouping modes.
- [X] Гарантировать complete grouped children и правильную page-size semantics.
- [X] Добавить lazy Requests tab, privacy-safe rows, provider/cost/event labels.
- [X] Покрыть timezone/DST, empty/first/middle/last pages и Usage parity.

### 13.8 Settings API/UI и обслуживание Unibase

- [X] Реализовать GET/POST Settings с revision conflict и тремя provider groups.
- [X] Перенести auto-review preference из header с legacy URL/cookie migration.
- [X] Реализовать Reset Unibase с сохранением settings/source registry и `reset_empty`.
- [X] Реализовать staging Full reindex, progress polling, integrity check и atomic swap.
- [X] Добавить modal accessibility, dirty-draft rules и cache invalidation.

### 13.9 Provider selector и branding

- [X] Добавить selector в порядке All, Codex, Claude, OpenCode; default/invalid provider → All.
- [X] Добавить neutral All mark и OpenCode provider identity без смешивания с MeterMesh brand.
- [X] Обновить runtime/package/launcher/docs/screenshot/verification skill до MeterMesh 2.0.0.
- [X] Проверить desktop, 390px, keyboard/focus, reduced motion и dark palette.

### 13.10 Cleanup и release readiness

- [X] Удалить production old Claude DB/full Codex scan paths только после parity/performance verification.
- [X] Выполнить полную privacy/performance/regression матрицу раздела 15.
- [X] Выполнить targeted branding/provider string audit.
- [-] External repository rename исключён из scope: он требует отдельного явного подтверждения и не выполняется автоматически.

---

## 14. Critical files

Создать:

- [unibase.py](unibase.py)
- [codex_usage.py](codex_usage.py)
- [opencode_usage.py](opencode_usage.py)
- [tests/test_unibase.py](tests/test_unibase.py)
- [tests/test_multisource_dedup.py](tests/test_multisource_dedup.py)
- [tests/test_opencode_usage.py](tests/test_opencode_usage.py)
- [tests/test_all_provider.py](tests/test_all_provider.py)
- [tests/test_settings_api.py](tests/test_settings_api.py)
- [tests/test_requests_api.py](tests/test_requests_api.py)

Изменить:

- [claude_usage.py](claude_usage.py)
- [dashboard_api.py](dashboard_api.py)
- [src/main.js](src/main.js)
- [src/styles.css](src/styles.css)
- [vite.config.mjs](vite.config.mjs)
- [index.html](index.html)
- [package.json](package.json), [package-lock.json](package-lock.json)
- [dev.mjs](dev.mjs)
- [README.md](README.md), [CHANGELOG.md](CHANGELOG.md), [LICENSE](LICENSE)
- launcher, screenshot и verification skill.

---

## 15. Verification

### Backup discovery

- normalized manifest source;
- direct provider root и fixed nested `.codex`/`.claude`/OpenCode legacy copy;
- incomplete copy detection;
- ambiguous roots;
- Windows paths imported on Linux;
- exclusion of non-usage/credential/derived files.

### Duplicate handling

Codex fixtures:

- byte-identical rollout copies;
- strict prefix + later superset;
- multiple sequential backup supersets;
- divergent non-conflicting copies;
- real record conflict;
- exact + fallback mixed copies;
- fallback-only copies без response IDs;
- subagent child/parent identities.

Claude fixtures:

- same UUID/message ID across live and multiple backups;
- partial overlap;
- conflicting payload variants;
- ID-less normalized hash fallback;
- primary + subagent transcripts.

OpenCode fixtures:

- live WAL database snapshot и standalone normalized backup;
- same `message.id` across live and multiple backups;
- conflicting payload for one message ID;
- ID-less fallback identity;
- late update через overlap cursor и deleted-message reconciliation;
- input/output/reasoning/cache read/cache write/cost extraction;
- unknown schema capability failure retains stale committed data;
- credential/account/content tables присутствуют, но никогда не читаются и не попадают в Unibase/API.

Assertions:

- один logical event считается один раз;
- disabling duplicate source не меняет totals, если другой enabled source сохраняет occurrence;
- disabling sole source убирает event только из active projection;
- re-enable восстанавливает без reparsing;
- conflicting winner меняется deterministically при выключении higher-priority source.

### Source reconciliation

- JSONL append, partial line, truncate, replace, delete;
- OpenCode late update, WAL snapshot consistency, database replace и deleted-message reconciliation;
- source unavailable retains stale snapshot;
- failed enumeration не удаляет occurrences;
- successful full scan reconciles missing files только этого source;
- concurrent scans/mutations не создают дублей.

### Reset/reindex

- Reset сохраняет settings/source IDs и оставляет visible reset_empty;
- auto-refresh после Reset заблокирован;
- Reindex live + checked backups восстанавливает данные;
- unchecked backups не парсятся;
- GET во время reindex видит old generation;
- failed staging build не повреждает current DB;
- mutation conflicts возвращают 409.

### All aggregation

- missing/invalid provider defaults to `all`;
- All totals равны сумме Codex + Claude + OpenCode scopes на одной generation;
- одинаковые native session/message/model IDs разных providers не склеиваются;
- provider-qualified model labels стабильны;
- recorded/estimated/unavailable cost breakdown не маскируется под billing total;
- cache read/write корректно суммируются и compatibility cached alias не удваивает tokens.

### Requests

- All и все три providers;
- все grouping modes и timezone/DST boundaries;
- first/middle/last/empty page;
- page size считает events или branches;
- grouped branch содержит всех children;
- snapshot стабилизирует numbered pages;
- grouped/request totals согласованы с Usage.

### Privacy

Рекурсивно проверить отсутствие raw session/response/UUID/message IDs, absolute paths, prompts, responses, tools, cwd, attachments, OpenCode account/credential/auth данных и fixture secrets в normal APIs/errors. В Settings отдавать только safe relative backup folder names.

### Performance

- unique content blob парсится один раз;
- backup supersets reuse hashes;
- unchanged scans делают inventory checks;
- append читает только новые bytes;
- OpenCode incremental scan читает только changed/overlap message rows и не загружает `part`/credential content;
- checkbox changes rebuild active projection without filesystem scan;
- Usage/Requests работают по SQL и не materialize full raw history;
- RSS значительно ниже текущих ~500 MB.

### Commands/browser/branding

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- `node --test tests/*.test.mjs`
- `npm run build`
- `npm run check`
- dataviz dark palette validator;
- browser verify для MeterMesh header, All и трёх providers, трёх tabs, Settings modal, backup toggles, reset/reindex progress, grouping/pagination, keyboard/focus, reduced motion и 390px viewport;
- targeted final search: old product branding удалён, provider-specific Codex/Claude/OpenCode strings сохранены.
