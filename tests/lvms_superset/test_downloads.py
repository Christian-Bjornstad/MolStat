from __future__ import annotations

import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from molstat.lvms.downloads import (
    CsvArrivalDetector,
    DownloadError,
    DownloadStatus,
    finalize_csv,
    open_local,
)


class DownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_ignores_existing_and_requires_two_stable_polls(self) -> None:
        (self.root / "existing.csv").write_text("old", encoding="utf-8")
        detector = CsvArrivalDetector(self.root)
        detector.start()
        new = self.root / "new.CSV"
        new.write_text("new", encoding="utf-8")
        self.assertEqual(detector.poll(), DownloadStatus.WAITING)
        self.assertEqual(detector.poll(), DownloadStatus.DETECTED)
        self.assertEqual(detector.detected_path(), new.resolve())

    def test_detects_existing_csv_when_edge_replaces_its_content(self) -> None:
        existing = self.root / "PAT-DIT-ANTALL-OU.csv"
        existing.write_bytes(b"old")
        detector = CsvArrivalDetector(self.root)
        detector.start()

        existing.write_bytes(b"new report content")

        self.assertEqual(detector.poll(), DownloadStatus.WAITING)
        self.assertEqual(detector.poll(), DownloadStatus.DETECTED)
        self.assertEqual(detector.detected_path(), existing.resolve())

    def test_reports_ambiguity_and_missing_detected_file(self) -> None:
        detector = CsvArrivalDetector(self.root)
        detector.start()
        first = self.root / "one.csv"
        second = self.root / "two.csv"
        first.write_text("1", encoding="utf-8")
        second.write_text("2", encoding="utf-8")
        self.assertEqual(detector.poll(), DownloadStatus.AMBIGUOUS)

        second.unlink()
        self.assertEqual(detector.poll(), DownloadStatus.WAITING)
        self.assertEqual(detector.poll(), DownloadStatus.DETECTED)
        first.unlink()
        self.assertEqual(detector.poll(), DownloadStatus.MISSING)

    def test_open_local_uses_injected_opener_without_reading(self) -> None:
        csv = self.root / "report.csv"
        csv.write_text("synthetic", encoding="utf-8")
        opened: list[str] = []
        open_local(csv, opener=opened.append)
        self.assertEqual(opened, [str(csv)])

    def test_rejects_unsafe_open_targets_and_relative_detector(self) -> None:
        with self.assertRaises(DownloadError):
            CsvArrivalDetector(Path("relative"))
        invalid = (self.root / "missing.csv", self.root / "folder.csv")
        invalid[1].mkdir()
        for path in invalid:
            with self.subTest(path=path):
                with self.assertRaises(DownloadError) as caught:
                    open_local(path, opener=lambda value: None)
                self.assertNotIn(str(path), str(caught.exception))

    def test_waits_while_temporary_download_exists(self) -> None:
        detector = CsvArrivalDetector(self.root)
        detector.start()
        temporary = self.root / "report.csv.crdownload"
        completed = self.root / "report.csv"
        temporary.write_bytes(b"partial")
        completed.write_bytes(b"partial")

        self.assertEqual(detector.poll(), DownloadStatus.WAITING)
        temporary.unlink()
        self.assertEqual(detector.poll(), DownloadStatus.WAITING)
        self.assertEqual(detector.poll(), DownloadStatus.DETECTED)

    def test_rejects_temporary_file_already_present_at_baseline(self) -> None:
        (self.root / "lingering.csv.crdownload").write_bytes(b"partial")
        detector = CsvArrivalDetector(self.root)

        with self.assertRaisesRegex(DownloadError, "temporary"):
            detector.start()

    def test_rejects_unexpected_non_csv_file(self) -> None:
        detector = CsvArrivalDetector(self.root)
        detector.start()
        (self.root / "unexpected.pdf").write_bytes(b"not a report csv")
        (self.root / "report.csv").write_bytes(b"synthetic")

        self.assertEqual(detector.poll(), DownloadStatus.AMBIGUOUS)

    def test_finalize_csv_moves_without_overwriting(self) -> None:
        source = self.root / "generated.csv"
        source.write_bytes(b"synthetic")
        destination_directory = self.root / "rådata"
        destination_directory.mkdir()

        destination = finalize_csv(
            source, destination_directory, "one__2026-08-01__2026-08-07.csv"
        )

        self.assertTrue(destination.is_file())
        self.assertFalse(source.exists())
        destination.write_bytes(b"existing")
        second = self.root / "second.csv"
        second.write_bytes(b"new")
        with self.assertRaises(DownloadError):
            finalize_csv(second, destination_directory, destination.name)
        self.assertTrue(second.is_file())
        self.assertEqual(destination.read_bytes(), b"existing")

    def test_finalize_csv_moves_across_filesystems(self) -> None:
        source = self.root / "generated.csv"
        source.write_bytes(b"synthetic")
        destination_directory = self.root / "rådata"
        destination_directory.mkdir()

        with patch("shutil.os.rename", side_effect=OSError(errno.EXDEV, "cross-device")):
            destination = finalize_csv(source, destination_directory, "report.csv")

        self.assertEqual(destination.read_bytes(), b"synthetic")
        self.assertFalse(source.exists())

    def test_finalize_csv_rejects_unsafe_paths_and_suffixes(self) -> None:
        source = self.root / "source.csv"
        source.write_bytes(b"synthetic")
        outside = self.root / "outside"
        outside.mkdir()
        invalid = (
            (Path("source.csv"), self.root, "target.csv"),
            (source, Path("relative"), "target.csv"),
            (source, self.root, "../target.csv"),
            (source, self.root, "target.txt"),
        )
        for source_path, directory, filename in invalid:
            with self.subTest(source=source_path, directory=directory, filename=filename):
                with self.assertRaises(DownloadError) as caught:
                    finalize_csv(source_path, directory, filename)
                self.assertNotIn(str(self.root), str(caught.exception))


if __name__ == "__main__":
    unittest.main()

