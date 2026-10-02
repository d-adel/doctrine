import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab.store import Store


def queued(store, cls="sweep", needs=(), short=False, recipe="r", for_ref=""):
    return store.submit(recipe, {}, "a" * 40, list(needs), cls, short, for_ref, now=0.0)


class Queue(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def test_submit_and_get_round_trip(self):
        job_id = self.store.submit("check-line", {"name": "suite"}, "b" * 40, ["os=linux"], "gate", True, now=5.0)
        job = self.store.get(job_id)
        self.assertEqual(job["params"], {"name": "suite"})
        self.assertEqual(job["needs"], ["os=linux"])
        self.assertTrue(job["short"])
        self.assertEqual(job["state"], "queued")

    def test_an_unknown_class_is_refused(self):
        with self.assertRaises(ValueError):
            self.store.submit("r", {}, "a" * 40, [], "urgent", False)

    def test_claim_runs_the_policy_and_marks_the_job_running(self):
        queued(self.store, "sweep")
        gate = queued(self.store, "gate")
        job = self.store.claim("spare", ["os=linux"], now=1.0)
        self.assertEqual(job["id"], gate)
        self.assertEqual(job["state"], "running")
        self.assertEqual(job["worker"], "spare")
        self.assertEqual(job["attempts"], 1)

    def test_gate_job_overtakes_a_queued_sweep(self):
        first = queued(self.store, "sweep")
        self.store.claim("spare", [], now=1.0)
        queued(self.store, "sweep")
        gate = queued(self.store, "gate")
        self.assertEqual(self.store.claim("spare", [], now=2.0)["id"], gate)
        self.assertEqual(self.store.get(first)["state"], "running")

    def test_claim_counts_overtakes_on_older_eligible_jobs(self):
        older = queued(self.store, "sweep")
        queued(self.store, "gate")
        self.store.claim("spare", [], now=1.0)
        self.assertEqual(self.store.get(older)["overtaken"], 1)

    def test_nothing_eligible_claims_nothing(self):
        queued(self.store, "gate", needs=["os=windows"])
        self.assertIsNone(self.store.claim("spare", ["os=linux"], now=1.0))

    def test_heartbeat_belongs_to_the_claiming_worker(self):
        job_id = queued(self.store)
        self.store.claim("spare", [], now=1.0)
        self.assertTrue(self.store.heartbeat(job_id, "spare", now=2.0))
        self.assertFalse(self.store.heartbeat(job_id, "desktop", now=2.0))

    def test_finish_records_done_or_failed(self):
        good = queued(self.store)
        self.store.claim("spare", [], now=1.0)
        self.assertTrue(self.store.finish(good, "spare", 0, {"metrics": {"x": 1.0}}, now=3.0))
        self.assertEqual(self.store.get(good)["state"], "done")
        bad = queued(self.store)
        self.store.claim("spare", [], now=4.0)
        self.store.finish(bad, "spare", 2, {}, now=5.0)
        self.assertEqual(self.store.get(bad)["state"], "failed")
        self.assertEqual(self.store.get(bad)["exit_code"], 2)

    def test_cancel_stops_heartbeats(self):
        job_id = queued(self.store)
        self.store.claim("spare", [], now=1.0)
        self.assertTrue(self.store.cancel(job_id, now=2.0))
        self.assertFalse(self.store.heartbeat(job_id, "spare", now=3.0))
        self.assertFalse(self.store.finish(job_id, "spare", 0, {}, now=4.0))
        self.assertEqual(self.store.get(job_id)["state"], "cancelled")

    def test_requeue_lost_puts_a_silent_job_back(self):
        job_id = queued(self.store)
        self.store.claim("spare", [], now=1.0)
        self.assertEqual(self.store.requeue_lost(10.0, now=100.0), [job_id])
        job = self.store.get(job_id)
        self.assertEqual(job["state"], "queued")
        self.assertEqual(job["worker"], "")

    def test_requeue_lost_twice_fails_as_lost(self):
        job_id = queued(self.store)
        self.store.claim("spare", [], now=1.0)
        self.store.requeue_lost(10.0, now=100.0)
        self.store.claim("desktop", [], now=101.0)
        self.store.requeue_lost(10.0, now=200.0)
        job = self.store.get(job_id)
        self.assertEqual(job["state"], "failed")
        self.assertEqual(job["result"], {"reason": "lost"})

    def test_a_paused_worker_claims_nothing(self):
        queued(self.store, "gate")
        self.store.set_paused("desktop", True)
        self.assertIsNone(self.store.claim("desktop", [], now=1.0))
        self.assertTrue(self.store.paused("desktop"))
        self.store.set_paused("desktop", False)
        self.assertIsNotNone(self.store.claim("desktop", [], now=2.0))

    def test_workers_are_seen_by_claim(self):
        self.store.claim("spare", ["os=linux", "gpu"], now=7.0)
        worker = self.store.workers()[0]
        self.assertEqual(worker["name"], "spare")
        self.assertEqual(worker["labels"], ["gpu", "os=linux"])
        self.assertEqual(worker["seen"], 7.0)

    def test_jobs_filter_by_for_ref(self):
        queued(self.store, for_ref="sweep:os=linux:abc")
        queued(self.store)
        self.assertEqual(len(self.store.jobs(for_ref="sweep:os=linux:abc")), 1)


if __name__ == "__main__":
    unittest.main()
