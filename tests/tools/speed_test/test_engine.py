import unittest
from unittest.mock import patch

from fuzztoolbox.tools.speed_test.engine import SpeedTestCancelled, SpeedTestEngine


class FakeTransport:
    def __init__(self):
        self.download_calls = 0

    def download(self, size):
        self.download_calls += 1
        return size, 0.02

    def upload(self, size):
        return size, 0.04


class SpeedTestEngineTests(unittest.TestCase):
    @patch("fuzztoolbox.tools.speed_test.engine.time.perf_counter")
    def test_run_reports_all_measurements(self, clock):
        clock.side_effect = (value / 10 for value in range(1000))
        events = []
        result = SpeedTestEngine(FakeTransport(), parallelism=2).run(
            lambda phase, progress, value: events.append((phase, progress, value))
        )

        self.assertAlmostEqual(result.latency_ms, 20.0)
        self.assertAlmostEqual(result.jitter_ms, 0.0)
        self.assertGreater(result.download_mbps, 0)
        self.assertGreater(result.upload_mbps, 0)
        self.assertGreaterEqual(result.uploaded_bytes, 2_500_000)
        self.assertEqual(events[-1][:2], ("complete", 1.0))

    def test_cancel_before_latency_samples_stops_test(self):
        engine = SpeedTestEngine(FakeTransport())

        def cancel_after_warmup(phase, progress, value):
            engine.cancel()

        with self.assertRaises(SpeedTestCancelled):
            engine.run(cancel_after_warmup)


if __name__ == "__main__":
    unittest.main()
