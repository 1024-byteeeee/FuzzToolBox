import unittest

from fuzztoolbox.tools.timer.countdown import CountdownTimer, StopwatchTimer, format_duration


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class CountdownTimerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.timer = CountdownTimer(10, self.clock)

    def test_running_countdown_uses_elapsed_time(self):
        self.timer.start()
        self.clock.value += 3.25
        self.assertAlmostEqual(self.timer.remaining, 6.75)
        self.assertAlmostEqual(self.timer.progress, 0.325)

    def test_pause_and_resume_preserve_remaining_time(self):
        self.timer.start()
        self.clock.value += 4
        self.timer.pause()
        self.clock.value += 20
        self.assertEqual(self.timer.remaining, 6)
        self.timer.resume()
        self.clock.value += 2
        self.assertEqual(self.timer.remaining, 4)

    def test_completion_and_reset(self):
        self.timer.start()
        self.clock.value += 11
        self.assertEqual(self.timer.remaining, 0)
        self.assertEqual(self.timer.state, "finished")
        self.timer.reset()
        self.assertEqual(self.timer.state, "idle")
        self.assertEqual(self.timer.remaining, 10)

    def test_duration_validation_and_running_guard(self):
        with self.assertRaises(ValueError):
            CountdownTimer(0)
        self.timer.set_duration(0)
        self.assertEqual(self.timer.remaining, 0)
        self.assertEqual(self.timer.progress, 0)
        with self.assertRaises(ValueError):
            self.timer.start()
        self.timer.set_duration(10)
        self.timer.start()
        with self.assertRaises(RuntimeError):
            self.timer.set_duration(20)

    def test_duration_format_rounds_remaining_fraction_up(self):
        self.assertEqual(format_duration(0), "00:00:00.000")
        self.assertEqual(format_duration(0.1), "00:00:00.100")
        self.assertEqual(format_duration(1.0001), "00:00:01.001")
        self.assertEqual(format_duration(3661.234), "01:01:01.234")


class StopwatchTimerTests(unittest.TestCase):
    def test_start_pause_resume_and_reset(self):
        clock = FakeClock()
        stopwatch = StopwatchTimer(clock)
        stopwatch.start()
        clock.value += 1.234
        self.assertAlmostEqual(stopwatch.elapsed, 1.234)
        stopwatch.pause()
        clock.value += 10
        self.assertAlmostEqual(stopwatch.elapsed, 1.234)
        stopwatch.resume()
        clock.value += 0.5
        self.assertAlmostEqual(stopwatch.elapsed, 1.734)
        stopwatch.reset()
        self.assertEqual(stopwatch.elapsed, 0)
        self.assertEqual(stopwatch.state, "idle")


if __name__ == "__main__":
    unittest.main()
