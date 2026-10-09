import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import upload_data


class UploadDataTests(unittest.TestCase):
    def test_missing_directory_returns_1(self):
        missing = ROOT / "data" / "does-not-exist-upload-test"
        self.assertEqual(upload_data.upload_csvs_to_postgres(missing), 1)

    def test_empty_directory_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(upload_data.upload_csvs_to_postgres(tmp), 1)

    def test_incomplete_dataset_does_not_connect(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "olist_customers_dataset.csv").write_text(
                "a\n1\n", encoding="utf-8"
            )
            with patch.object(
                upload_data,
                "get_db_engine",
                side_effect=AssertionError("engine called"),
            ):
                self.assertEqual(upload_data.upload_csvs_to_postgres(tmp), 1)


if __name__ == "__main__":
    unittest.main()
