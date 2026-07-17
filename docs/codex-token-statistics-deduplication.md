# Корректный подсчет token usage в Codex rollout

## 1. Цель

Документ описывает единственный принятый алгоритм подсчета token usage для текущей программы.

Официальный метод:

```text
глобальная дедупликация по паре:
last_token_usage + rate_limits
```



Другие способы оценки в программе использовать не нужно.

## 2. Источники данных

### 2.1. Session rollout

Основной источник token usage:

```text
~/.codex/sessions/**/*.jsonl
```

Необходимое событие:

```json
{
  "type": "event_msg",
  "payload": {
    "type": "token_count",
    "info": {
      "total_token_usage": {},
      "last_token_usage": {
        "input_tokens": 100000,
        "cached_input_tokens": 95000,
        "output_tokens": 500,
        "reasoning_output_tokens": 200,
        "total_tokens": 100500
      }
    },
    "rate_limits": {}
  }
}
```

Для расчета используются только:

```text
payload.info.last_token_usage
payload.rate_limits
timestamp
```

### 2.2. SQLite logs

Файл:

```text
~/.codex/logs_2.sqlite
```

SQLite можно использовать для:

- проверки отдельных запросов;
- поиска transport/server errors;
- контроля периода хранения;
- диагностики работы parser.

SQLite нельзя использовать как единственный источник общего количества token usage. В текущем наборе он содержит только часть activity, присутствующей в session rollout.

## 3. Причина завышения статистики

### 3.1. Копирование истории в subagent

При создании дочернего агента Codex создает новый rollout и копирует в него историю родительского thread.

В copied history попадают не только сообщения и tool calls, но и прежние события:

```text
event_msg.type = token_count
```

При создании следующего дочернего агента та же история копируется еще раз.

В результате один реальный usage record может присутствовать во множестве JSONL-файлов.

На исследованном наборе:

```text
threads:             158
subagent threads:    152
spawn edges:         150
max children:        134
```

Поэтому простой обход всех JSONL без дедупликации дал десятки миллиардов токенов, хотя фактический расход существенно меньше.

### 3.2. `total_token_usage` является накопительным

Поле:

```text
payload.info.total_token_usage
```

является накопительным состоянием конкретного rollout.

Его нельзя суммировать между событиями:

```python
# Неправильно
sum(
    event["payload"]["info"]["total_token_usage"]["total_tokens"]
    for event in events
)
```

Также нельзя брать последнее `total_token_usage` каждого thread и суммировать thread между собой. Parent и child могут содержать одну и ту же историю.

### 3.3. `last_token_usage` также копируется

Поле:

```text
payload.info.last_token_usage
```

содержит usage одного обновления, но это обновление повторяется в copied history.

Поэтому следующий код также неправильный:

```python
# Неправильно
sum(
    event["payload"]["info"]["last_token_usage"]["total_tokens"]
    for event in all_rollout_events
)
```

## 4. Принятое правило дедупликации

Два события считаются одной записью usage, если у них одновременно совпадают:

```text
last_token_usage
rate_limits
```

Сравнение должно выполняться после нормализации значений и канонической JSON-сериализации.

Если два независимых response случайно получили полностью одинаковые usage и rate limit snapshot, текущая программа считает их одной записью.

Это принятое бизнес-правило. Оно намеренно отдает приоритет защите от многократного учета copied history.

## 5. Нормализация usage

### 5.1. Порядок полей

Usage приводится к tuple с фиксированным порядком:

```python
USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
```

Нормализация:

```python
def normalize_usage(usage: dict) -> tuple[int, int, int, int, int]:
    return tuple(int(usage.get(name) or 0) for name in USAGE_FIELDS)
```

Отсутствующее значение и `null` преобразуются в `0`.

### 5.2. Нормализация rate limits

Порядок ключей JSON не должен влиять на дедупликацию.

```python
def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
```

`rate_limits` нормализуется так:

```python
rate_key = canonical_json(payload.get("rate_limits"))
```

Если `rate_limits` отсутствует, сериализуется `null`.

### 5.3. Deduplication key

Логический ключ:

```python
dedup_key = (
    normalize_usage(last_token_usage),
    canonical_json(rate_limits),
)
```

Для хранения в базе можно вычислять SHA-256:

```python
def make_dedup_key(usage: dict, rate_limits: object) -> str:
    value = {
        "usage": normalize_usage(usage),
        "rate_limits": rate_limits,
    }

    canonical = canonical_json(value)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

## 6. Алгоритм подсчета

### 6.1. Общий алгоритм

1. Найти все `~/.codex/sessions/**/*.jsonl`.
2. Читать каждый файл построчно.
3. Каждую строку независимо декодировать как JSON.
4. Пропускать malformed JSON, увеличивая диагностический счетчик.
5. Выбирать только `type == "event_msg"`.
6. Выбирать только `payload.type == "token_count"`.
7. Получить `payload.info.last_token_usage`.
8. Получить `payload.rate_limits`.
9. Построить `dedup_key`.
10. Глобально хранить только одну запись на `dedup_key`.
11. Если ключ уже встречался, оставить запись с минимальным timestamp.
12. После обхода просуммировать usage уникальных записей.

Дедупликация должна быть глобальной, а не внутри одного файла или thread.

### 6.2. Почему хранится минимальный timestamp

Исходное usage-событие появляется раньше copied history.

Для одного `dedup_key` используется:

```python
canonical_timestamp = min(all_occurrence_timestamps)
```

Это позволяет не относить старый usage к дате создания нового subagent.

Если исходный rollout уже удален, минимальный доступный timestamp может быть временем первой сохранившейся копии. Такие периоды необходимо помечать как потенциально неполные.

### 6.3. Полный пример parser

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


@dataclass(frozen=True)
class UsageRecord:
    timestamp: datetime
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int
    source_file: str
    source_line: int


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def normalize_usage(usage: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return tuple(int(usage.get(name) or 0) for name in USAGE_FIELDS)


def make_dedup_key(
    usage: dict[str, Any],
    rate_limits: Any,
) -> str:
    canonical = canonical_json(
        {
            "usage": normalize_usage(usage),
            "rate_limits": rate_limits,
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def collect_usage(root: Path) -> tuple[dict[str, UsageRecord], int]:
    unique: dict[str, UsageRecord] = {}
    malformed_lines = 0

    for path in root.rglob("*.jsonl"):
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line_number, line in enumerate(stream, start=1):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    malformed_lines += 1
                    continue

                if event.get("type") != "event_msg":
                    continue

                payload = event.get("payload") or {}
                if payload.get("type") != "token_count":
                    continue

                info = payload.get("info") or {}
                usage = info.get("last_token_usage") or {}
                rate_limits = payload.get("rate_limits")

                input_tokens, cached_tokens, output_tokens, reasoning_tokens, total_tokens = (
                    normalize_usage(usage)
                )

                record = UsageRecord(
                    timestamp=parse_timestamp(event["timestamp"]),
                    input_tokens=input_tokens,
                    cached_input_tokens=cached_tokens,
                    output_tokens=output_tokens,
                    reasoning_output_tokens=reasoning_tokens,
                    total_tokens=total_tokens,
                    source_file=str(path),
                    source_line=line_number,
                )

                key = make_dedup_key(usage, rate_limits)
                current = unique.get(key)

                if current is None or record.timestamp < current.timestamp:
                    unique[key] = record

    return unique, malformed_lines
```

## 7. Формулы итоговых метрик

Для каждой уникальной записи:

```python
input_with_cache = cached_input_tokens
input_without_cache = input_tokens - cached_input_tokens
input_total = input_tokens
output = output_tokens
total = total_tokens
```

Глобальные значения:

```python
summary = {
    "records": len(unique),
    "input_with_cache": sum(x.cached_input_tokens for x in unique.values()),
    "input_without_cache": sum(
        x.input_tokens - x.cached_input_tokens
        for x in unique.values()
    ),
    "input_total": sum(x.input_tokens for x in unique.values()),
    "output": sum(x.output_tokens for x in unique.values()),
    "reasoning_output": sum(
        x.reasoning_output_tokens
        for x in unique.values()
    ),
    "total": sum(x.total_tokens for x in unique.values()),
}
```

`reasoning_output_tokens` уже является частью `output_tokens` в обычных событиях. Его не нужно дополнительно прибавлять к total.

## 8. Группировка по дням

Timestamp в JSONL хранится в UTC. Группировку необходимо выполнять после преобразования в требуемый IANA timezone.

Пример для Москвы:

```python
from zoneinfo import ZoneInfo

timezone = ZoneInfo("Europe/Moscow")
local_day = record.timestamp.astimezone(timezone).date()
```

Не следует использовать timezone операционной системы как неявную настройку production-программы.

Рекомендуется хранить timezone в конфигурации:

```text
STATISTICS_TIMEZONE=Europe/Moscow
```



## 10. Покрытие периода

Текущие основные данные начинаются с 11 июля 2026 года.

Поэтому запрос статистики за 07-17 июля без архивных данных имеет следующие ограничения:

```text
07-10 июля: отсутствуют в основном наборе
11 июля: данные начинаются не с начала суток
16-17 июля: model usage в текущем наборе не найден
```

Официальное значение 3 803 713 318 относится только к фактически доступным основным session-данным.

Архивы нельзя автоматически объединять с основной базой без повторной глобальной дедупликации. Один и тот же `dedup_key` может присутствовать и в основной базе, и в архиве.

## 11. Структура таблицы

Рекомендуемая таблица:

```sql
CREATE TABLE usage_records (
    dedup_key TEXT PRIMARY KEY,
    first_seen_at_utc INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    cached_input_tokens INTEGER NOT NULL,
    uncached_input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    reasoning_output_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    source_rollout TEXT,
    source_line INTEGER,
    algorithm_version INTEGER NOT NULL
);
```

Поле `first_seen_at_utc` обновляется, если найдено более раннее occurrence того же ключа.

Пример upsert:

```sql
INSERT INTO usage_records (
    dedup_key,
    first_seen_at_utc,
    input_tokens,
    cached_input_tokens,
    uncached_input_tokens,
    output_tokens,
    reasoning_output_tokens,
    total_tokens,
    source_rollout,
    source_line,
    algorithm_version
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(dedup_key) DO UPDATE SET
    first_seen_at_utc = MIN(
        usage_records.first_seen_at_utc,
        excluded.first_seen_at_utc
    ),
    source_rollout = CASE
        WHEN excluded.first_seen_at_utc < usage_records.first_seen_at_utc
        THEN excluded.source_rollout
        ELSE usage_records.source_rollout
    END,
    source_line = CASE
        WHEN excluded.first_seen_at_utc < usage_records.first_seen_at_utc
        THEN excluded.source_line
        ELSE usage_records.source_line
    END;
```

## 12. Инкрементальное обновление

Программа может обрабатывать только новые или измененные JSONL-файлы, но таблица deduplication keys должна оставаться общей для всей истории.

Рекомендуется хранить:

```text
file path
file size
mtime
last processed byte offset
last processed line
parser version
```

При изменении алгоритма нормализации необходимо увеличить `algorithm_version` и перестроить статистику полностью.

Нельзя удалять старый deduplication key только потому, что исходный rollout был перемещен или архивирован.

## 13. Что нельзя делать

Нельзя считать количество запросов так:

```text
COUNT(all token_count events)
```

Нельзя считать total так:

```text
SUM(threads.tokens_used)
SUM(total_token_usage snapshots)
SUM(last_token_usage across every rollout without deduplication)
```

Нельзя выполнять дедупликацию только внутри одного файла:

```python
# Неправильно: копии находятся в разных rollout
for path in files:
    unique_in_file = set()
```

Нельзя определять server rejection по:

```text
output_tokens == 0
task_complete
turn_aborted без проверки error logs
```

## 14. Диагностические счетчики

Каждый запуск parser должен возвращать:

```text
processed_files
processed_lines
malformed_lines
token_count_events
unique_usage_records
duplicate_usage_events
minimum_timestamp
maximum_timestamp
```

Полезная проверка:

```python
duplicate_usage_events = token_count_events - unique_usage_records
```

Резкое уменьшение duplicate count после обновления parser обычно означает ошибку дедупликации или неполный набор файлов.

## 15. Обязательные тесты

### 15.1. Копия между rollout

```text
Given: одно usage-событие присутствует в 20 JSONL-файлах
Expected: одна запись и один набор токенов
```

### 15.2. Разный порядок rate limit keys

```text
Given: rate_limits содержит одинаковые значения с разным порядком ключей
Expected: один dedup_key
```

### 15.3. Разные rate limits

```text
Given: usage совпадает, rate_limits различается
Expected: две записи
```

### 15.4. Одинаковая пара usage + rate limits

```text
Given: usage и rate_limits полностью совпадают
Expected: одна запись независимо от файла, thread и timestamp
```

### 15.5. Ранний timestamp

```text
Given: одна копия имеет timestamp T2, исходное событие имеет T1, T1 < T2
Expected: first_seen_at = T1
```

### 15.6. Malformed JSON

```text
Given: одна поврежденная строка между корректными событиями
Expected: строка пропущена, остальные события обработаны
```

### 15.7. Null token fields

```text
Given: token field отсутствует или равен null
Expected: значение нормализуется в 0
```

### 15.8. Reasoning output

```text
Given: output_tokens=1000, reasoning_output_tokens=600
Expected: total не увеличивается дополнительно на 600
```

## 16. Итоговое правило для программы

В программе должен остаться только следующий расчет:

```text
1. Прочитать все token_count из session rollout.
2. Нормализовать last_token_usage.
3. Канонизировать rate_limits.
4. Построить глобальный dedup_key из usage + rate_limits.
5. Оставить одно событие на dedup_key.
6. Для даты использовать минимальный timestamp.
7. Суммировать usage уникальных записей.
```
