import unittest

from src.syscheck import build_report


class TestSyscheck(unittest.TestCase):
    def test_build_report_has_keys(self):
        report = build_report("one.one.one.one", "1.1.1.1", ["/"])
        self.assertIn("platform", report)
        self.assertIn("cpu", report)
        self.assertIn("memory", report)
        self.assertIn("disk", report)
        self.assertIn("network", report)


if __name__ == "__main__":
    unittest.main()
