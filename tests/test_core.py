import tempfile
import unittest
import sqlite3
from pathlib import Path

from traceloom.classifier import classify
from traceloom.fixtures import recovery_fixture, sample_runs
from traceloom.metrics import summarize, watchdog_experiment
from traceloom.models import Run, Span
from traceloom.report import write_report
from traceloom.store import TraceStore
from traceloom.watchdog import repeated_tool_loop, semantic_progress
from traceloom.recovery import RecoveryAttempt, compare_recovery, evaluate_attempt
from traceloom.privacy import PrivacyPolicy, REDACTED_EMAIL, REDACTED_SECRET, sanitize_run
from traceloom.cli import main


class CoreTests(unittest.TestCase):
    def test_fixture_classification(self):
        labels={r.run_id:classify(r) for r in sample_runs()}
        self.assertEqual(labels["run-002"],"infinite_loop")
        self.assertEqual(labels["run-003"],"timeout")
        self.assertEqual(labels["run-004"],"refusal")
        self.assertIsNone(labels["run-001"])
    def test_progress_finds_different_action_loop(self):
        run=sample_runs()[1]
        self.assertTrue(semantic_progress(run.spans).flagged)
        self.assertFalse(repeated_tool_loop(run.spans))
    def test_repeated_detector_finds_literal_loop(self):
        run=sample_runs()[4]
        self.assertTrue(repeated_tool_loop(run.spans))
        self.assertFalse(semantic_progress(run.spans).flagged)
    def test_invalid_window(self):
        with self.assertRaises(ValueError): semantic_progress(sample_runs()[0].spans,1)
    def test_rollup_uses_cost_per_success(self):
        result=summarize(sample_runs())
        self.assertEqual(result["runs"],5); self.assertEqual(result["successes"],2)
        self.assertGreater(result["cost_per_success_usd"],0)
    def test_experiment_improves_loop_recall_without_false_alert(self):
        result=watchdog_experiment(sample_runs())
        self.assertGreater(result["semantic_progress"]["recall"],result["repeated_tool"]["recall"])
        self.assertEqual(result["semantic_progress"]["false_alert_rate"],0)
    def test_store_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            store=TraceStore(Path(d)/"t.db"); runs=sample_runs()
            for r in runs: store.ingest(r)
            self.assertEqual(store.runs(),runs)
    def test_privacy_firewall_redacts_seeded_secrets_before_storage(self):
        span=Span("private","s1",0,"tool","lookup",0,1,
            input={"query":"email alice@example.com bearer abcdefghijklmnop","arguments":{"api_key":"sk-test-secret","safe":"ok"},"raw_prompt":"drop me"},
            output={"result":"password=hunter2","debug_dump":"drop me too"})
        run=Run("private","Contact alice@example.com",True,(span,))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"t.db"; store=TraceStore(path)
            accounting=store.ingest(run)
            raw=path.read_bytes()
            for secret in (b"alice@example.com",b"abcdefghijklmnop",b"sk-test-secret",b"hunter2",b"drop me"):
                self.assertNotIn(secret,raw)
            saved=store.runs()[0]
            self.assertIn(REDACTED_EMAIL,saved.task)
            self.assertEqual(saved.spans[0].input["arguments"]["api_key"],REDACTED_SECRET)
            self.assertGreaterEqual(accounting["redacted_values"],4)
            self.assertEqual(accounting["dropped_fields"],2)
    def test_privacy_policy_can_narrow_allowlist(self):
        run=Run("narrow","task",True,(Span("narrow","s",0,"tool","x",0,1,input={"query":"keep","arguments":{"safe":1}}),))
        clean,stats=sanitize_run(run,PrivacyPolicy(input_allowlist=("query",),output_allowlist=()))
        self.assertEqual(clean.spans[0].input,{"query":"keep"})
        self.assertEqual(stats.dropped_fields,1)
    def test_ttl_purge_is_deterministic_and_cascades(self):
        with tempfile.TemporaryDirectory() as d:
            store=TraceStore(Path(d)/"t.db")
            store.ingest(sample_runs()[0],ingested_at_ms=1000,ttl_ms=500)
            store.ingest(sample_runs()[1],ingested_at_ms=1000,ttl_ms=1000)
            self.assertEqual(store.purge_expired(1499),[])
            self.assertEqual(store.purge_expired(1500),["run-001"])
            self.assertEqual([r.run_id for r in store.runs()],["run-002"])
            self.assertEqual(store.privacy_summary()["runs_accounted"],1)
    def test_invalid_ttl_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as d:
            store=TraceStore(Path(d)/"t.db")
            with self.assertRaises(ValueError): store.ingest(sample_runs()[0],ttl_ms=0)
            self.assertEqual(store.runs(),[])
    def test_purge_cli_removes_expired_trace(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"t.db"; store=TraceStore(path)
            store.ingest(sample_runs()[0],ingested_at_ms=10,ttl_ms=5)
            self.assertEqual(main(["purge","--db",str(path),"--now-ms","15"]),0)
            self.assertEqual(store.runs(),[])
    def test_privacy_accounting_is_in_report(self):
        with tempfile.TemporaryDirectory() as d:
            j,h=Path(d)/"r.json",Path(d)/"r.html"
            store=TraceStore(Path(d)/"t.db")
            for run in sample_runs(): store.ingest(run)
            report=write_report(store.runs(),str(j),str(h),store.privacy_summary())
            self.assertEqual(report["privacy"]["runs_accounted"],5)
            self.assertGreater(report["privacy"]["retained_field_rate"],0)
    def test_store_rejects_duplicate_sequence(self):
        span=Span("x","1",0,"tool","a",0,1)
        run=Run("x","task",False,(span,Span("x","2",0,"tool","b",1,1)))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): TraceStore(Path(d)/"t.db").ingest(run)
    def test_report_writes_json_and_html(self):
        with tempfile.TemporaryDirectory() as d:
            j,h=Path(d)/"r.json",Path(d)/"r.html"
            report=write_report(sample_runs(),str(j),str(h))
            self.assertTrue(j.exists() and h.exists()); self.assertEqual(report["summary"]["runs"],5)
            self.assertEqual(report["recovery_experiment"]["recommended"],"after-reservation")
            self.assertIn("TraceLoom",h.read_text())
    def test_recovery_prefers_safe_low_cost_checkpoint(self):
        run,attempts=recovery_fixture()
        result=compare_recovery(run,attempts)
        self.assertEqual(result["recommended"],"after-reservation")
        self.assertEqual(result["decision"],"resume")
        self.assertEqual(result["cost_savings_vs_full_restart_usd"],.007)
    def test_recovery_surfaces_duplicate_side_effect_risk(self):
        run,attempts=recovery_fixture()
        result=compare_recovery(run,attempts)
        by_name={item["name"]:item for item in result["attempts"]}
        self.assertFalse(by_name["full-restart"]["safe_for_active_replay"])
        self.assertIn("reserve",by_name["full-restart"]["repeated_non_idempotent_span_ids"])
        self.assertTrue(by_name["after-reservation"]["safe_for_active_replay"])
    def test_recovery_requires_simulated_results(self):
        run,_=recovery_fixture()
        unsafe=Span(run.run_id,"live",4,"tool","notify",0,1,cost_usd=.1)
        with self.assertRaises(ValueError):
            evaluate_attempt(run,RecoveryAttempt("bad",2,(unsafe,),True))
    def test_recovery_requires_full_restart_comparator(self):
        run,attempts=recovery_fixture()
        with self.assertRaises(ValueError): compare_recovery(run,attempts[1:])
    def test_recovery_rejects_unknown_checkpoint(self):
        run,attempts=recovery_fixture()
        invalid=RecoveryAttempt("invalid",99,attempts[-1].replay,True)
        with self.assertRaises(ValueError): evaluate_attempt(run,invalid)

if __name__=="__main__": unittest.main()

