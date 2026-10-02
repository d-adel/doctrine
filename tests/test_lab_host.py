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

    def test_windows_subprocesses_open_no_window(self):
        seen = []
        real_popen, real_run, real_windows = host.subprocess.Popen, host.subprocess.run, host.WINDOWS
        host.subprocess.Popen = lambda *args, **kwargs: seen.append(kwargs)
        host.subprocess.run = lambda *args, **kwargs: seen.append(kwargs)
        try:
            host.WINDOWS = True
            host.start(["bash", "-c", "true"], ".", {})
            host.hidden_run(["git", "status"])
        finally:
            host.subprocess.Popen, host.subprocess.run, host.WINDOWS = real_popen, real_run, real_windows
        self.assertEqual(len(seen), 2)
        for kwargs in seen:
            self.assertTrue(kwargs.get("creationflags", 0) & 0x08000000)

    def test_cpu_load_is_a_percentage(self):
        load = host.cpu_load(0.2)
        self.assertGreaterEqual(load, 0.0)
        self.assertLessEqual(load, 100.0)

    def test_owner_is_never_present_off_windows(self):
        if not host.WINDOWS:
            self.assertFalse(host.Presence().present())

    def test_suspend_resume_and_kill_a_process_tree(self):
        process = host.start(["bash", "-c", "for i in 1 2 3 4 5 6 7 8 9 10; do echo $i; sleep 0.2; done"], None, None)
        host.suspend(process)
        time.sleep(0.5)
        self.assertIsNone(process.poll())
        host.resume(process)
        host.kill(process)
        process.wait(timeout=10)
        self.assertIsNotNone(process.poll())


class Desk:
    def __init__(self):
        self.now = 0.0
        self.last = -10.0 ** 6
        self.full = False
        self.where = (0, 0)

    def clock(self):
        return self.now

    def since_input(self):
        return self.now - self.last

    def fullscreen(self):
        return self.full

    def cursor(self):
        return self.where

    def presence(self, minutes=3, window=300, cursor=False):
        return host.Presence(minutes, window, self.since_input, self.fullscreen, self.clock,
                             self.cursor if cursor else None)

    def sample(self, presence, start, stop, every=10.0, typing=False, moving=0):
        seen = []
        moment = start
        while moment < stop:
            self.now = moment
            if typing:
                self.last = moment
            if moving:
                self.where = (self.where[0] + moving, self.where[1])
            seen.append(presence.present())
            moment += every
        return seen


class Presence(unittest.TestCase):
    def test_a_stray_input_every_three_minutes_is_not_presence(self):
        desk = Desk()
        presence = desk.presence()
        seen = []
        for event in range(0, 3600, 180):
            desk.last = float(event)
            seen += desk.sample(presence, float(event), float(event + 180))
        self.assertNotIn(True, seen)

    def test_input_in_three_distinct_minutes_is_presence(self):
        desk = Desk()
        presence = desk.presence()
        self.assertEqual(desk.sample(presence, 1200.0, 1320.0, typing=True), [False] * 12)
        self.assertTrue(desk.sample(presence, 1320.0, 1321.0, typing=True)[0])

    def test_input_within_one_minute_counts_once(self):
        desk = Desk()
        presence = desk.presence(minutes=2)
        self.assertNotIn(True, desk.sample(presence, 600.0, 660.0, every=1.0, typing=True))

    def test_presence_ends_once_its_minutes_leave_the_window(self):
        desk = Desk()
        presence = desk.presence()
        desk.sample(presence, 0.0, 600.0, typing=True)
        quiet = desk.sample(presence, 600.0, 1200.0)
        self.assertTrue(quiet[0])
        self.assertEqual(quiet.index(False), 18)
        self.assertNotIn(True, quiet[18:])

    def test_a_fullscreen_app_is_presence_without_input(self):
        desk = Desk()
        desk.full = True
        self.assertTrue(desk.presence().present())

    def test_with_the_cursor_rule_input_that_leaves_the_cursor_still_is_not_presence(self):
        desk = Desk()
        presence = desk.presence(cursor=True)
        self.assertNotIn(True, desk.sample(presence, 0.0, 600.0, typing=True))

    def test_with_the_cursor_rule_input_that_moves_the_cursor_is_presence(self):
        desk = Desk()
        presence = desk.presence(cursor=True)
        seen = desk.sample(presence, 0.0, 600.0, typing=True, moving=40)
        self.assertFalse(seen[0])
        self.assertTrue(seen[-1])

    def test_with_the_cursor_rule_a_cursor_that_jitters_a_pixel_is_not_presence(self):
        desk = Desk()
        presence = desk.presence(cursor=True)
        self.assertNotIn(True, desk.sample(presence, 0.0, 600.0, typing=True, moving=1))

    def test_with_the_cursor_rule_a_fullscreen_app_is_presence(self):
        desk = Desk()
        desk.full = True
        self.assertTrue(desk.presence(cursor=True).present())

    def test_the_window_and_the_minutes_come_from_the_arguments(self):
        desk = Desk()
        presence = desk.presence(minutes=2, window=90)
        self.assertTrue(desk.sample(presence, 0.0, 70.0, typing=True)[-1])
        self.assertFalse(desk.sample(presence, 160.0, 161.0)[0])


if __name__ == "__main__":
    unittest.main()
