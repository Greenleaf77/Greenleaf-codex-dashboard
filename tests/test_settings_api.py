import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import dashboard_api
import unibase


class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.path = self.root / "metermesh" / "unibase.sqlite3"
        self.db = unibase.Unibase(self.path)
        self.codex_root = self.root / ".codex"
        (self.codex_root / "sessions").mkdir(parents=True)
        self.db.register_source(unibase.DiscoveredSource(
            "codex-live", "codex", "live", self.codex_root, "live", "Live Codex",
            True, 1000, None, None, "ready",
        ))
        backup_root = self.root / "backup"
        (backup_root / "sessions").mkdir(parents=True)
        self.db.register_source(unibase.DiscoveredSource(
            "codex-backup", "codex", "normalized_backup", backup_root, "backup-one", "Backup one",
            False, 500, "snapshot-1", "2026-07-16T00:00:00Z", "ready",
        ))

        class Handler(dashboard_api.DashboardHandler):
            pass

        Handler.unibase_path = self.path
        Handler.db_path = self.codex_root / "state_5.sqlite"
        Handler.claude_projects_path = self.root / ".claude" / "projects"
        Handler.opencode_db_path = self.root / "opencode" / "opencode.db"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def request(self, path, method="GET", payload=None, content_type="application/json", cookie=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.base_url + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", content_type)
        if cookie:
            request.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read())
            finally:
                error.close()

    def test_get_and_apply_settings_are_safe_and_revisioned(self):
        status, payload = self.request("/api/settings")
        self.assertEqual(status, 200)
        self.assertEqual(payload["revision"], 1)
        self.assertEqual(len(payload["backups"]["codex"]), 1)
        encoded = json.dumps(payload)
        self.assertNotIn(str(self.root), encoded)

        body = {
            "revision": payload["revision"],
            "ignore_codex_auto_review": True,
            "backups": [{"source_id": "codex-backup", "enabled": True}],
        }
        status, applied = self.request("/api/settings", "POST", body)
        self.assertEqual(status, 200)
        self.assertTrue(applied["ignore_codex_auto_review"])
        self.assertTrue(applied["backups"]["codex"][0]["enabled"])

        status, conflict = self.request("/api/settings", "POST", body)
        self.assertEqual(status, 409)
        self.assertIn("error", conflict)

    def test_post_requires_json_and_strict_fields(self):
        status, _ = self.request("/api/settings", "POST", {"revision": 1}, content_type="text/plain")
        self.assertEqual(status, 400)
        status, _ = self.request("/api/settings", "POST", {"revision": 1})
        self.assertEqual(status, 400)

    def test_reset_confirmation_preserves_settings_and_registry(self):
        self.db.update_settings(1, True)
        status, _ = self.request("/api/unibase/reset", "POST", {"confirmation": "wrong"})
        self.assertEqual(status, 400)
        status, payload = self.request("/api/unibase/reset", "POST", {"confirmation": "RESET UNIBASE"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["unibase"]["state"], "reset_empty")
        self.assertTrue(payload["ignore_codex_auto_review"])
        self.assertEqual(len(payload["backups"]["codex"]), 1)

    def test_staging_reindex_succeeds_and_status_is_pollable(self):
        operation_id = self.db.create_operation("full_reindex")
        dashboard_api.reindex_worker(self.path, operation_id)

        status = unibase.Unibase(self.path).operation_status(operation_id)
        self.assertEqual(status["operation"]["state"], "succeeded")
        self.assertTrue(unibase.Unibase(self.path).integrity_check())

    def test_reindex_publish_does_not_break_existing_reader(self):
        reader = self.db.connect(readonly=True)
        self.addCleanup(reader.close)
        reader.execute("begin")
        before = reader.execute("select generation from app_settings where id = 1").fetchone()[0]
        operation_id = self.db.create_operation("full_reindex")

        dashboard_api.reindex_worker(self.path, operation_id)

        self.assertEqual(reader.execute("select generation from app_settings where id = 1").fetchone()[0], before)
        self.assertEqual(unibase.Unibase(self.path).operation_status(operation_id)["operation"]["state"], "succeeded")

    def test_reindex_keeps_main_database_when_external_codex_inventory_is_unavailable(self):
        self.db.upsert_source_file(
            "codex-live",
            "external:root:file",
            "codex_rollout",
            size=1,
            mtime_ns=1,
        )
        operation_id = self.db.create_operation("full_reindex")

        dashboard_api.reindex_worker(self.path, operation_id, codex_state_db=self.codex_root / "missing.sqlite")

        database = unibase.Unibase(self.path)
        self.assertEqual(database.operation_status(operation_id)["operation"]["state"], "failed")
        self.assertIn("external:root:file", database.source_file_keys("codex-live"))

    def test_reindex_requires_provided_state_inventory_before_external_checkpoints_exist(self):
        operation_id = self.db.create_operation("full_reindex")

        dashboard_api.reindex_worker(self.path, operation_id, codex_state_db=self.codex_root / "missing.sqlite")

        database = unibase.Unibase(self.path)
        self.assertEqual(database.operation_status(operation_id)["operation"]["state"], "failed")
        self.assertEqual(len(database.sources("codex")), 2)

    def test_mutations_conflict_with_running_operation(self):
        self.db.create_operation("full_reindex")
        settings = dashboard_api.settings_payload(self.path)
        body = {
            "revision": settings["revision"],
            "ignore_codex_auto_review": False,
            "backups": [{"source_id": "codex-backup", "enabled": False}],
        }
        status, _ = self.request("/api/settings", "POST", body)
        self.assertEqual(status, 409)
        status, _ = self.request("/api/unibase/reset", "POST", {"confirmation": "RESET UNIBASE"})
        self.assertEqual(status, 409)

    def test_reset_waits_for_import_and_remains_reset_empty(self):
        entered = threading.Event()
        release = threading.Event()
        source = self.db.sources("codex")[0]

        def paused_import(*_args, **_kwargs):
            entered.set()
            release.wait(2)

        with patch.object(dashboard_api, "import_codex_source", side_effect=paused_import):
            import_thread = threading.Thread(target=dashboard_api.import_registered_source, args=(self.db, source))
            import_thread.start()
            self.assertTrue(entered.wait(1))
            reset_thread = threading.Thread(target=self.db.reset)
            reset_thread.start()
            self.assertTrue(reset_thread.is_alive())
            release.set()
            import_thread.join()
            reset_thread.join()

        self.assertEqual(self.db.settings()["state"], "reset_empty")

    def test_first_api_request_migrates_legacy_preference_cookie(self):
        status, _ = self.request("/data.json?provider=codex", cookie="ignore_codex_auto_review_v2=1")

        self.assertEqual(status, 200)
        settings = self.db.settings()
        self.assertTrue(settings["ignore_codex_auto_review"])
        self.assertTrue(settings["legacy_preference_migrated"])

    def test_settings_discovers_new_backup_without_restart(self):
        snapshot = self.codex_root / "add_stat" / "new-snapshot"
        rollout = snapshot / "root" / "sessions" / "2026" / "07" / "16" / "rollout-a.jsonl"
        rollout.parent.mkdir(parents=True)
        rollout.write_text("{}\n", encoding="utf-8")
        (snapshot / "snapshot.json").write_text(json.dumps({
            "format": unibase.SNAPSHOT_FORMAT,
            "version": 1,
            "id": "new-snapshot",
            "provider": "codex",
            "root": "root",
            "label": "New snapshot",
        }), encoding="utf-8")

        status, payload = self.request("/api/settings")

        self.assertEqual(status, 200)
        self.assertTrue(any(source["label"] == "New snapshot" for source in payload["backups"]["codex"]))


if __name__ == "__main__":
    unittest.main()
