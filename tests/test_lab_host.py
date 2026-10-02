import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab import host


class Probes(unittest.TestCase):
    def test_parse_proc_stat_counts_idle_and_iowait_as_idle(self):
        busy, total = host.parse_proc_stat("cpu  10 0 5 80 5 0 0 0 0 0\ncpu0 1 1 1 1 1\n")
        self.assertEqual((busy, total), (15, 100))

    def test_percent_between_two_samples(self):
        self.assertEqual(host.percent((10, 100), (30, 200)), 20.0)
        self.assertEqual(host.percent((10, 100), (10, 100)), 0.0)

    def test_parse_nvidia_takes_the_busiest_gpu(self):
        self.assertEqual(host.parse_nvidia("3\n57\n"), 57)
        self.assertIsNone(host.parse_nvidia(""))

    def test_descendants_walk_the_tree_once(self):
        pairs = [(2, 1, 0), (3, 2, 0), (4, 2, 0), (5, 9, 0), (1, 0, 0), (6, 6, 0)]
        self.assertEqual(sorted(host.descendants(pairs, 2)), [2, 3, 4])
        self.assertEqual(host.descendants(pairs, 6), [6])

    def test_descendants_skip_a_child_older_than_its_parent(self):
        processes = [(10, 1, 100), (11, 10, 150), (20, 10, 50), (21, 20, 60)]
        self.assertEqual(sorted(host.descendants(processes, 10)), [10, 11])

    def test_cpu_load_is_a_percentage(self):
        load = host.cpu_load(0.2)
        self.assertGreaterEqual(load, 0.0)
        self.assertLessEqual(load, 100.0)

    def test_owner_is_never_present_off_windows(self):
        if not host.WINDOWS:
            self.assertFalse(host.owner_present(600))

    def test_suspend_resume_and_kill_a_process_tree(self):
        process = host.start(["bash", "-c", "for i in 1 2 3 4 5 6 7 8 9 10; do echo $i; sleep 0.2; done"], None, None)
        host.suspend(process)
        time.sleep(0.5)
        self.assertIsNone(process.poll())
        host.resume(process)
        host.kill(process)
        process.wait(timeout=10)
        self.assertIsNotNone(process.poll())


if __name__ == "__main__":
    unittest.main()
