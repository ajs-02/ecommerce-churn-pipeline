import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ConnectionExitTests(unittest.TestCase):
    def test_closed_port_exits_1_without_printing_the_password(self):
        env = os.environ.copy()
        env["POSTGRES_HOST"] = "127.0.0.1"
        env["POSTGRES_PORT"] = "1"
        env["POSTGRES_USER"] = "unused"
        env["POSTGRES_PASSWORD"] = "unused-secret"
        env["POSTGRES_DB"] = "unused"
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "test_connection.py")],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("unused-secret", result.stdout)
        self.assertNotIn("unused-secret", result.stderr)
        self.assertIn("Failed to connect", result.stdout)


if __name__ == "__main__":
    unittest.main()
