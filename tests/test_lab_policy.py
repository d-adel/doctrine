import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab import policy
from lab.policy import Job


class Pick(unittest.TestCase):
    def test_higher_class_wins(self):
        self.assertEqual(policy.pick([Job(1, "sweep"), Job(2, "gate")], {"os=linux"}).id, 2)

    def test_older_wins_within_a_class(self):
        self.assertEqual(policy.pick([Job(1, "experiment"), Job(2, "experiment")], set()).id, 1)

    def test_gate_job_overtakes_a_queued_sweep(self):
        queue = [Job(1, "sweep"), Job(2, "sweep"), Job(3, "gate")]
        self.assertEqual(policy.pick(queue, set()).id, 3)

    def test_a_waited_short_job_moves_up_one_class(self):
        queue = [Job(1, "sweep"), Job(2, "sweep", waiting=True, short=True), Job(3, "experiment")]
        self.assertEqual(policy.pick(queue, set()).id, 2)

    def test_a_waited_long_job_is_not_boosted(self):
        queue = [Job(1, "experiment"), Job(2, "sweep", waiting=True, short=False)]
        self.assertEqual(policy.pick(queue, set()).id, 1)

    def test_the_boost_stops_at_gate(self):
        self.assertEqual(policy.rank(Job(1, "gate", waiting=True, short=True)), len(policy.CLASSES) - 1)

    def test_aging_moves_up_one_class_per_ten_overtakes(self):
        self.assertEqual(policy.rank(Job(1, "background", overtaken=9)), 0)
        self.assertEqual(policy.rank(Job(1, "background", overtaken=10)), 1)
        self.assertEqual(policy.rank(Job(1, "background", overtaken=20)), 2)

    def test_aging_stops_at_gate(self):
        self.assertEqual(policy.rank(Job(1, "background", overtaken=1000)), len(policy.CLASSES) - 1)

    def test_labels_must_cover_the_needs(self):
        queue = [Job(1, "gate", needs=frozenset({"os=windows"})), Job(2, "sweep")]
        self.assertEqual(policy.pick(queue, {"os=linux"}).id, 2)

    def test_nothing_eligible_picks_nothing(self):
        self.assertIsNone(policy.pick([Job(1, "gate", needs=frozenset({"gpu"}))], {"os=linux"}))

    def test_passed_over_counts_only_older_eligible_jobs(self):
        queue = [Job(1, "sweep"), Job(2, "sweep", needs=frozenset({"gpu"})), Job(3, "gate"), Job(4, "sweep")]
        self.assertEqual(policy.passed_over(queue, {"os=linux"}, queue[2]), [1])


if __name__ == "__main__":
    unittest.main()
