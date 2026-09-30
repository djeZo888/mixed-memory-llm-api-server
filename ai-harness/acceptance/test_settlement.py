"""Offline settlement contract tests against the actual additive SQLite schema.

No deployment(), SSH, systemctl, model, or live database access is performed.
"""
import importlib.util
import copy
import json
import pathlib
import sqlite3
import unittest


spec = importlib.util.spec_from_file_location(
    "settlement_readback", pathlib.Path(__file__).with_name("settlement-readback.py"))
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

SCHEMA = """
CREATE TABLE sessions(id TEXT PRIMARY KEY,title TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,status TEXT NOT NULL,context TEXT NOT NULL,workspace_id TEXT NOT NULL,native_session_id TEXT,deleted INTEGER NOT NULL DEFAULT 0,delete_requested INTEGER NOT NULL DEFAULT 0);
CREATE TABLE runs(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),workspace_id TEXT NOT NULL,kind TEXT NOT NULL,text TEXT NOT NULL,attachment_ids TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE events(session_id TEXT NOT NULL REFERENCES sessions(id),id INTEGER NOT NULL,type TEXT NOT NULL,run_id TEXT,created_at TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(session_id,id));
CREATE TABLE quarantined_workspaces(id TEXT PRIMARY KEY,reason TEXT NOT NULL);
CREATE TABLE h021_session_engines(session_id TEXT PRIMARY KEY REFERENCES sessions(id),engine_kind TEXT NOT NULL,engine_version TEXT,model_policy_version TEXT,workspace_id TEXT NOT NULL,active_turn_id TEXT,event_cursor INTEGER NOT NULL DEFAULT 0,ownership TEXT NOT NULL DEFAULT 'idle');
CREATE TABLE h021_gateway_requests(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,state TEXT NOT NULL,record TEXT NOT NULL);
CREATE TABLE h003_image_jobs(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,request_id TEXT NOT NULL,data TEXT NOT NULL,UNIQUE(session_id,request_id));
CREATE TABLE h003_image_lane(id INTEGER PRIMARY KEY CHECK(id=1),state TEXT NOT NULL);
CREATE TABLE h005_image_ownership(id INTEGER PRIMARY KEY CHECK(id=1),uncertain INTEGER NOT NULL CHECK(uncertain IN (0,1)));
"""


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript(SCHEMA)
        self.query = dict(sessionId="owned", runId="run-owned",
                          exactSource=helper.SOURCE, pilotId=helper.PILOT)
        self.binding = {"fixture": True, "exactSource": helper.SOURCE, "pilotId": helper.PILOT}
        self.session("owned")
        self.create_run("run-owned", "owned")
        self.event("done", {"runId": "run-owned"})

    def session(self, session, ownership="idle", engine="codex"):
        self.db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (session, "fixture", "now", "now", "idle", "{}", "ws-" + session, "native-" + session, 0, 0))
        self.db.execute("INSERT INTO h021_session_engines(session_id,engine_kind,workspace_id,ownership) VALUES(?,?,?,?)",
                        (session, engine, "ws-" + session, ownership))

    def create_run(self, run, session, state="completed"):
        self.db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)",
                        (run, session, "ws-" + session, "prompt", "fixture", "[]", state, "now", "now"))

    def event(self, kind, data, session="owned", run="run-owned"):
        cursor = self.db.execute("SELECT COALESCE(MAX(id),0)+1 FROM events WHERE session_id=?", (session,)).fetchone()[0]
        self.db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", (session, cursor, kind, run, "now", json.dumps(data)))

    def request(self, request="request-owned", session="owned", state="settled", **changes):
        record = {"id": request, "sessionId": session, "state": state,
                  "lane": "qwen3.8-27b-gpu0", "updatedAt": "fixture-time", **changes}
        self.db.execute("INSERT OR REPLACE INTO h021_gateway_requests VALUES(?,?,?,?)",
                        (request, session, state, json.dumps(record)))
        return record

    def image(self, image="image-owned", session="owned", state="completed", error=None, **changes):
        job = {"id": image, "sessionId": session, "runId": "run-" + session,
               "state": state, **changes}
        if error:
            job["error"] = {"code": error}
        self.db.execute("INSERT OR REPLACE INTO h003_image_jobs VALUES(?,?,?,?)",
                        (image, session, "request-" + image, json.dumps({"job": job})))

    def read(self):
        self.db.commit()
        before = self.db.total_changes
        result = helper.readback(self.db, self.query, self.binding)
        self.assertEqual(self.db.total_changes, before, "readback must not mutate ownership")
        self.assertFalse(self.db.in_transaction)
        return result

    def physical_release(self):
        self.db.executescript("""
            CREATE TABLE h036_physical_releases(recovery_id TEXT PRIMARY KEY,session_id TEXT NOT NULL,run_id TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,proof_sha256 TEXT NOT NULL,record TEXT NOT NULL);
            CREATE TABLE h036_released_requests(request_id TEXT PRIMARY KEY,recovery_id TEXT NOT NULL,original_record TEXT NOT NULL);
        """)
        self.db.execute("UPDATE runs SET status='interrupted' WHERE id='run-owned'")
        request = self.request(state="accepted", accounting={"inputTokens": 92607, "reservedOutputTokens": 65536})
        record = {
            "recoveryId": "recovery-owned", "proofSha256": "a" * 64, "snapshotSha256": "b" * 64,
            "physicalRelease": True, "outcome": "interrupted_unknown",
            "target": {"sessionId": "owned", "runId": "run-owned", "workspaceId": "ws-owned",
                       "threadId": "native-owned", "turnId": "turn-owned", "requestIds": ["request-owned"]},
            "priorOwnership": {"session_id": "owned", "workspace_id": "ws-owned", "engine_kind": "codex",
                               "ownership": "uncertain", "active_turn_id": "turn-owned"},
            "priorRun": {"id": "run-owned", "session_id": "owned", "workspace_id": "ws-owned", "status": "interrupted"},
            "priorSession": {"id": "owned", "workspace_id": "ws-owned", "native_session_id": "native-owned"},
        }
        self.db.execute("INSERT INTO h036_physical_releases VALUES(?,?,?,?,?,?)",
                        (record["recoveryId"], "owned", "run-owned", record["snapshotSha256"], record["proofSha256"], json.dumps(record)))
        self.db.execute("INSERT INTO h036_released_requests VALUES(?,?,?)",
                        ("request-owned", record["recoveryId"], json.dumps(request)))
        audit = {k: record[k] for k in ("recoveryId", "proofSha256", "physicalRelease", "outcome")}
        self.event("done", {**audit, "runId": "run-owned"})
        self.event("progress", {**audit, "kind": "cleanup", "label": helper.CLEANUP_LABEL})
        return record

    def assert_rejected(self):
        self.db.commit()
        before = self.db.total_changes
        with self.assertRaises(AssertionError):
            helper.readback(self.db, self.query, self.binding)
        self.assertEqual(self.db.total_changes, before)
        self.assertFalse(self.db.in_transaction)

    def test_physical_release_settles_interruption_without_success_or_usage_change(self):
        self.physical_release()
        original = self.db.execute("SELECT record FROM h021_gateway_requests").fetchone()[0]
        result = self.read()
        self.assertTrue(result["settled"])
        self.assertTrue(result["physicallySettledInterruptedUnknown"])
        self.assertFalse(result["completedSuccess"])
        self.assertEqual(result["evidence"]["runStatus"], "interrupted")
        receipt = result["evidence"]["requestReceipts"][0]
        self.assertEqual(receipt["state"], "accepted")
        self.assertEqual(receipt["accounting"], {"inputTokens": 92607, "reservedOutputTokens": 65536})
        self.assertEqual(receipt["physicalRelease"]["disposition"], "physically_released_interrupted_unknown")
        self.assertEqual(self.db.execute("SELECT record FROM h021_gateway_requests").fetchone()[0], original)

    def test_physical_release_identity_digest_and_outcome_drift_rejects(self):
        record = self.physical_release()
        changes = [("recoveryId", "other"), ("proofSha256", "c" * 64), ("snapshotSha256", "c" * 64),
                   ("outcome", "completed"), ("physicalRelease", False)]
        for key, value in changes:
            with self.subTest(key=key):
                changed = {**record, key: value}
                self.db.execute("UPDATE h036_physical_releases SET record=?", (json.dumps(changed),))
                self.assert_rejected()
        for section, keys in (("target", ("sessionId", "runId", "workspaceId", "threadId", "turnId")),
                              ("priorOwnership", ("ownership", "active_turn_id", "engine_kind")),
                              ("priorRun", ("status",)), ("priorSession", ("native_session_id",))):
            for key in keys:
                with self.subTest(section=section, key=key):
                    changed = copy.deepcopy(record)
                    changed[section][key] = "wrong"
                    self.db.execute("UPDATE h036_physical_releases SET record=?", (json.dumps(changed),))
                    self.assert_rejected()

    def test_physical_release_missing_or_mismatched_audit_rejects(self):
        self.physical_release()
        audit = list(self.db.execute("SELECT id,type,data FROM events WHERE id>1"))
        for event_id, kind, data in audit:
            for field, value in (("recoveryId", "wrong"), ("proofSha256", "c" * 64),
                                 ("outcome", "completed"), ("physicalRelease", False)):
                with self.subTest(kind=kind, field=field):
                    self.db.execute("UPDATE events SET data=? WHERE id=?", (json.dumps({**json.loads(data), field: value}), event_id))
                    self.assert_rejected()
                    self.db.execute("UPDATE events SET data=? WHERE id=?", (data, event_id))
            with self.subTest(kind=kind, missing=True):
                self.db.execute("DELETE FROM events WHERE id=?", (event_id,))
                self.assert_rejected()
                self.db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", ("owned", event_id, kind, "run-owned", "now", data))

    def test_physical_release_exact_mapping_and_original_bytes_required(self):
        record = self.physical_release()
        for ids in ([], ["different-request"], ["request-owned", "request-owned"], ["request-owned", "extra-request"]):
            with self.subTest(ids=ids):
                changed = copy.deepcopy(record)
                changed["target"]["requestIds"] = ids
                self.db.execute("UPDATE h036_physical_releases SET record=?", (json.dumps(changed),))
                self.assert_rejected()
        self.db.execute("UPDATE h036_physical_releases SET record=?", (json.dumps(record),))
        self.db.execute("UPDATE h021_gateway_requests SET record=record || ' '")
        self.assert_rejected()

    def test_physical_release_orphan_mapping_and_partial_schema_reject(self):
        self.physical_release()
        self.db.execute("UPDATE h036_released_requests SET recovery_id='missing'")
        self.assert_rejected()
        self.db.execute("DROP TABLE h036_released_requests")
        self.assert_rejected()

    def test_physical_release_new_turn_uses_same_history_without_old_request_replay(self):
        self.physical_release()
        original = self.db.execute("SELECT record FROM h021_gateway_requests").fetchone()[0]
        self.create_run("followup", "owned", "completed")
        self.event("done", {"runId": "followup"}, run="followup")
        self.query["runId"] = "followup"
        result = self.read()
        self.assertTrue(result["settled"])
        self.assertFalse(result["physicallySettledInterruptedUnknown"])
        self.assertTrue(result["completedSuccess"])
        self.assertEqual(result["evidence"]["engine"]["native_thread_id"], "native-owned")
        self.assertEqual(self.db.execute("SELECT record FROM h021_gateway_requests").fetchone()[0], original)
        self.request(request="new-pending", state="accepted")
        self.assertEqual(self.read()["evidence"]["unsettledRequests"], ["new-pending"])
        self.assertFalse(self.read()["settled"])

    def test_physical_release_unrelated_uncertain_stays_blocked_and_unchanged(self):
        self.physical_release()
        self.session("other", ownership="uncertain")
        self.create_run("run-other", "other", "interrupted")
        self.request(request="request-other", session="other", state="uncertain")
        self.db.execute("INSERT INTO quarantined_workspaces VALUES('ws-other','unknown')")
        before = list(self.db.execute("SELECT * FROM h021_gateway_requests WHERE session_id='other'"))
        self.assertTrue(self.read()["settled"])
        self.query.update(sessionId="other", runId="run-other")
        result = self.read()
        self.assertFalse(result["settled"])
        self.assertFalse(result["physicallySettledInterruptedUnknown"])
        self.assertEqual([tuple(v) for v in self.db.execute("SELECT * FROM h021_gateway_requests WHERE session_id='other'")], before)

    def test_physical_release_cannot_override_current_native_quarantine_or_image_gates(self):
        self.physical_release()
        self.db.execute("UPDATE h021_session_engines SET ownership='uncertain'")
        self.assertFalse(self.read()["settled"])
        self.db.execute("UPDATE h021_session_engines SET ownership='idle'")
        self.db.execute("INSERT INTO quarantined_workspaces VALUES('ws-owned','unknown')")
        self.assertFalse(self.read()["settled"])
        self.db.execute("DELETE FROM quarantined_workspaces")
        self.image(state="interrupted")
        self.assertFalse(self.read()["settled"])

    def test_physical_release_current_history_or_run_outcome_replacement_rejects(self):
        self.physical_release()
        self.db.execute("UPDATE runs SET status='completed'")
        self.assert_rejected()
        self.db.execute("UPDATE runs SET status='interrupted'")
        self.db.execute("UPDATE sessions SET native_session_id='replacement-thread'")
        self.assert_rejected()

    def test_completed_and_cancelled_settle(self):
        for status in ("completed", "cancelled"):
            with self.subTest(status=status):
                self.db.execute("UPDATE runs SET status=?", (status,))
                result = self.read()
                self.assertTrue(result["settled"])
                self.assertEqual(result["evidence"]["binding"], self.binding)

    def test_clean_failed_requires_source_bound_cleanup(self):
        self.db.execute("UPDATE runs SET status='failed'")
        self.assertFalse(self.read()["settled"])
        self.event("progress", {"kind": "cleanup", "label": "Owned engine container cleanup confirmed; interrupted work was not replayed"})
        self.assertTrue(self.read()["settled"])

    def test_interrupted_requires_exact_run_cleanup_and_preserves_outcome(self):
        self.db.execute("UPDATE runs SET status='interrupted'")
        self.assertFalse(self.read()["settled"])
        cleanup = {"kind": "cleanup", "label": "Owned engine container cleanup confirmed; interrupted work was not replayed"}
        self.event("progress", cleanup, run="another-run")
        self.assertFalse(self.read()["settled"])
        self.event("progress", cleanup)
        result = self.read()
        self.assertTrue(result["settled"])
        self.assertEqual(result["evidence"]["runStatus"], "interrupted")
        self.assertEqual(self.db.execute("SELECT status FROM runs").fetchone()[0], "interrupted")

    def test_clean_interrupted_still_requires_all_current_positive_ownership_gates(self):
        self.db.execute("UPDATE runs SET status='interrupted'")
        self.event("progress", {"kind": "cleanup", "label": "Owned engine container cleanup confirmed; interrupted work was not replayed"})
        self.assertTrue(self.read()["settled"])
        mutations = [
            ("UPDATE h021_session_engines SET ownership='uncertain'", "UPDATE h021_session_engines SET ownership='idle'"),
            ("UPDATE h021_session_engines SET active_turn_id='active'", "UPDATE h021_session_engines SET active_turn_id=NULL"),
            ("INSERT INTO quarantined_workspaces VALUES('ws-owned','unknown')", "DELETE FROM quarantined_workspaces"),
            ("UPDATE runs SET status='running'", "UPDATE runs SET status='interrupted'"),
        ]
        for mutation, restore in mutations:
            with self.subTest(mutation=mutation):
                self.db.execute(mutation)
                self.assertFalse(self.read()["settled"])
                self.db.execute(restore)
                self.assertTrue(self.read()["settled"])
        self.request(state="uncertain")
        self.assertFalse(self.read()["settled"])
        self.request(state="settled")
        self.image(state="failed", error="image_completion_unknown")
        self.assertFalse(self.read()["settled"])
        self.db.execute("DELETE FROM h003_image_jobs")
        self.create_run("active-successor", "owned", "queued")
        self.assertFalse(self.read()["settled"])
        self.db.execute("DELETE FROM runs WHERE id='active-successor'")
        self.db.execute("DELETE FROM events WHERE type='done'")
        self.assertFalse(self.read()["settled"])

    def test_failure_generic_progress_does_not_prove_cleanup(self):
        self.db.execute("UPDATE runs SET status='failed'")
        self.event("progress", {"kind": "cleanup", "label": "PID exited"})
        self.assertFalse(self.read()["settled"])

    def test_source_and_pilot_mismatch_rejected(self):
        for key in ("exactSource", "pilotId"):
            with self.subTest(key=key):
                changed = dict(self.query, **{key: "incorrect"})
                with self.assertRaises(AssertionError):
                    helper.validate(changed)

    def test_done_event_required_and_bound_to_run(self):
        self.db.execute("DELETE FROM events")
        self.assertFalse(self.read()["settled"])
        self.event("done", {"runId": "different-run"})
        self.assertFalse(self.read()["settled"])

    def test_native_active_uncertain_or_unknown_ownership_blocks(self):
        for state in ("active", "uncertain", "unrecognized", ""):
            with self.subTest(state=state):
                self.db.execute("UPDATE h021_session_engines SET ownership=?", (state,))
                self.assertFalse(self.read()["settled"])

    def test_active_turn_blocks_idle_record(self):
        self.db.execute("UPDATE h021_session_engines SET active_turn_id='turn-owned'")
        self.assertFalse(self.read()["settled"])

    def test_active_owned_successor_blocks(self):
        self.create_run("next-owned", "owned", "running")
        result = self.read()
        self.assertFalse(result["settled"])
        self.assertEqual(result["evidence"]["activeRuns"], [{"id": "next-owned", "status": "running"}])

    def test_owned_workspace_quarantine_blocks(self):
        self.db.execute("INSERT INTO quarantined_workspaces VALUES('ws-owned','native_cleanup_unknown')")
        self.assertFalse(self.read()["settled"])

    def test_each_pending_request_state_blocks(self):
        for state in ("queued", "counting", "accepted", "draining", "uncertain", "unknown"):
            with self.subTest(state=state):
                self.request(state=state)
                result = self.read()
                self.assertFalse(result["settled"])
                self.assertEqual(result["evidence"]["unsettledRequests"], ["request-owned"])

    def test_request_accounting_preserved_per_request(self):
        first = self.request(accounting={"inputTokens": 470, "reservedOutputTokens": 1024, "promptTokens": 472, "completionTokens": 31})
        second = self.request(request="request-followup", accounting={"inputTokens": 510, "reservedOutputTokens": 1024, "promptTokens": 512, "completionTokens": 47})
        result = self.read()
        self.assertTrue(result["settled"])
        self.assertEqual(result["evidence"]["requestReceipts"], [first, second])

    def test_pending_unknown_interrupted_and_ambiguous_images_block(self):
        for state, error in (("queued", None), ("running", None), ("saving", None),
                             ("awaiting_approval", None), ("interrupted", None), ("unknown", None),
                             ("failed", "image_completion_unknown"), ("cancelled", "server_stopped"),
                             ("failed", "server_restarted")):
            with self.subTest(state=state, error=error):
                self.image(state=state, error=error)
                result = self.read()
                self.assertFalse(result["settled"])
                self.assertEqual(result["evidence"]["imagePending"], ["image-owned"])

    def test_clean_terminal_images_do_not_block(self):
        for state in ("completed", "cancelled", "failed"):
            with self.subTest(state=state):
                self.image(state=state)
                self.assertTrue(self.read()["settled"])

    def test_unrelated_session_work_and_global_lane_do_not_block(self):
        self.session("other", ownership="uncertain")
        self.create_run("run-other", "other", "running")
        self.request(request="request-other", session="other", state="uncertain")
        self.image(image="image-other", session="other", state="interrupted", error="image_completion_unknown")
        self.db.execute("INSERT INTO quarantined_workspaces VALUES('ws-other','unknown')")
        self.db.execute("INSERT INTO h003_image_lane VALUES(1,'quarantined')")
        self.db.execute("INSERT INTO h005_image_ownership VALUES(1,1)")
        self.assertTrue(self.read()["settled"])

    def test_mismatched_request_ownership_rejects(self):
        self.request(sessionId="different-session")
        self.db.commit()
        with self.assertRaises(AssertionError):
            helper.readback(self.db, self.query, self.binding)

    def test_mismatched_image_ownership_rejects(self):
        self.image(sessionId="different-session")
        self.db.commit()
        with self.assertRaises(AssertionError):
            helper.readback(self.db, self.query, self.binding)

    def test_missing_or_unknown_engine_rejects(self):
        self.db.execute("UPDATE h021_session_engines SET engine_kind='unknown'")
        self.db.commit()
        with self.assertRaises(AssertionError):
            helper.readback(self.db, self.query, self.binding)
        self.db.execute("DELETE FROM h021_session_engines")
        self.db.commit()
        with self.assertRaises(AssertionError):
            helper.readback(self.db, self.query, self.binding)

    def test_interrupted_run_never_settles(self):
        self.db.execute("UPDATE runs SET status='interrupted'")
        self.assertFalse(self.read()["settled"])


if __name__ == "__main__":
    unittest.main()
