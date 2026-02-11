from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from core.logging_utils import create_session_logger


class LoggingTests(unittest.TestCase):
    def test_create_session_logger_creates_timestamped_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-suite-logs-") as temp_dir:
            logger, log_path = create_session_logger(log_dir=temp_dir, debug=True)
            logger.info("startup loop=v1 model=test")

            path = Path(log_path)
            self.assertTrue(path.exists())
            self.assertRegex(path.name, r"^session_\d{8}_\d{6}\.log$")

            content = path.read_text(encoding="utf-8")
            self.assertIn("startup loop=v1 model=test", content)

    def test_debug_logs_are_written_even_when_debug_flag_is_false(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-suite-logs-") as temp_dir:
            logger, log_path = create_session_logger(log_dir=temp_dir, debug=False)
            logger.debug("request payload: sample")

            content = Path(log_path).read_text(encoding="utf-8")
            self.assertIn("request payload: sample", content)


if __name__ == "__main__":
    unittest.main()
