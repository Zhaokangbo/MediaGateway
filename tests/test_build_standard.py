import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("quality_build", Path(__file__).resolve().parents[1] / "scripts/build-quality-zlm.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class StandardCheck(unittest.TestCase):
    def commands(self):
        return [dict(file="/src/" + name, command="c++ -std=gnu++11 -c file.cpp")
                for name in ("json_value.cpp", "WebHook.cpp", "RtpSequenceStats.cpp")]

    def test_consistent_cpp11(self):
        self.assertEqual(len(build.check_cpp_standards(self.commands())), 3)

    def test_reject_mixed_and_missing(self):
        mixed = self.commands()
        mixed[1]["command"] = "c++ -std=gnu++17 -c file.cpp"
        with self.assertRaises(RuntimeError):
            build.check_cpp_standards(mixed)
        with self.assertRaises(RuntimeError):
            build.check_cpp_standards(self.commands()[:2])

    def test_last_standard_wins(self):
        commands = self.commands()
        commands[0]["command"] = "c++ -std=gnu++11 -std=gnu++17 -c file.cpp"
        with self.assertRaises(RuntimeError):
            build.check_cpp_standards(commands)


if __name__ == "__main__":
    unittest.main(verbosity=2)
