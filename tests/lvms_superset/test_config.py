from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from molstat.lvms.config import (
    ConfigError,
    load_app_config,
    validate_app_config,
    validate_config,
)


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.temp_root = Path(self.temporary_directory.name)
        self.repo_root = self.temp_root / "repository"
        self.repo_root.mkdir()

    def test_accepts_https_landing_url_and_external_profile(self) -> None:
        profile_directory = self.temp_root / "profile"

        config = validate_config(
            {
                "landing_url": "https://lvms.ous-hf.no/clims/",
                "profile_directory": str(profile_directory),
            },
            repository_root=self.repo_root,
            allowed_profile_root=self.temp_root,
        )

        self.assertEqual(config.landing_url, "https://lvms.ous-hf.no/clims/")
        self.assertEqual(config.expected_origin, "https://lvms.ous-hf.no")
        self.assertEqual(config.profile_directory, profile_directory.resolve())

    def test_accepts_matching_explicit_expected_origin(self) -> None:
        config = validate_config(
            {
                "landing_url": "https://lvms.ous-hf.no/clims",
                "expected_origin": "https://lvms.ous-hf.no",
                "profile_directory": str(self.temp_root / "profile"),
            },
            repository_root=self.repo_root,
            allowed_profile_root=self.temp_root,
        )

        self.assertEqual(config.expected_origin, "https://lvms.ous-hf.no")

    def test_rejects_explicit_expected_origin_that_does_not_match_landing_url(self) -> None:
        for configured_origin in (
            "https://other.example.invalid",
            " https://lvms.ous-hf.no ",
        ):
            with self.subTest(configured_origin=configured_origin):
                with self.assertRaisesRegex(ConfigError, "expected_origin"):
                    validate_config(
                        {
                            "landing_url": "https://lvms.ous-hf.no/clims",
                            "expected_origin": configured_origin,
                            "profile_directory": str(self.temp_root / "profile"),
                        },
                        repository_root=self.repo_root,
                        allowed_profile_root=self.temp_root,
                    )

    def test_rejects_insecure_or_sensitive_landing_urls(self) -> None:
        invalid_urls = (
            "http://lvms.example.invalid/",
            "https://user:pass@lvms.example.invalid/",
            "https://lvms.example.invalid/?token=x",
            "https://lvms.example.invalid/#patient",
        )

        for landing_url in invalid_urls:
            with self.subTest(landing_url=landing_url):
                with self.assertRaises(ConfigError):
                    validate_config(
                        {
                            "landing_url": landing_url,
                            "profile_directory": str(self.temp_root / "profile"),
                        },
                        repository_root=self.repo_root,
                        allowed_profile_root=self.temp_root,
                    )

    def test_rejects_example_landing_url_before_edge_is_started(self) -> None:
        with self.assertRaisesRegex(ConfigError, "Oppsett"):
            validate_config(
                {
                    "landing_url": "https://lvms.example.invalid/clims",
                    "profile_directory": str(self.temp_root / "profile"),
                },
                repository_root=self.repo_root,
                allowed_profile_root=self.temp_root,
            )

    def test_rejects_profile_inside_repository(self) -> None:
        with self.assertRaisesRegex(ConfigError, "outside the repository"):
            validate_config(
                {
                    "landing_url": "https://lvms.ous-hf.no/",
                    "profile_directory": str(self.repo_root / "edge-profile"),
                },
                repository_root=self.repo_root,
                allowed_profile_root=self.temp_root,
            )

    def test_rejects_profile_outside_local_application_data(self) -> None:
        allowed_profile_root = self.temp_root / "local-app-data"
        allowed_profile_root.mkdir()

        with self.assertRaisesRegex(ConfigError, "local application-data"):
            validate_config(
                {
                    "landing_url": "https://lvms.ous-hf.no/",
                    "profile_directory": str(self.temp_root / "shared-profile"),
                },
                repository_root=self.repo_root,
                allowed_profile_root=allowed_profile_root,
            )

    def test_accepts_safe_download_directory(self) -> None:
        local = self.temp_root / "local-app-data"
        local.mkdir()
        downloads = local / "LVMS-STAT" / "downloads"
        raw = {
            "landing_url": "https://lvms.ous-hf.no/",
            "profile_directory": str(local / "LVMS-STAT" / "edge-profile"),
            "download_directory": str(downloads),
        }

        config = validate_app_config(
            raw, repository_root=self.repo_root, allowed_local_root=local
        )

        self.assertEqual(config.download_directory, downloads.resolve())

    def test_rejects_unsafe_download_directories(self) -> None:
        local = self.temp_root / "local-app-data"
        local.mkdir()
        base = {
            "landing_url": "https://lvms.ous-hf.no/",
            "profile_directory": str(local / "profile"),
            "download_directory": str(self.temp_root / "downloads"),
        }
        invalid = (
            {**base, "download_directory": "relative/downloads"},
            {**base, "download_directory": str(self.repo_root / "downloads")},
            {**base, "download_directory": str(self.temp_root / "shared-downloads")},
        )
        for raw in invalid:
            with self.subTest(raw=raw):
                with self.assertRaises(ConfigError):
                    validate_app_config(
                        raw,
                        repository_root=self.repo_root,
                        allowed_local_root=local,
                    )

    def test_load_app_config_rejects_non_object_json(self) -> None:
        path = self.temp_root / "app-config.json"
        path.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "JSON object"):
            load_app_config(
                path,
                repository_root=self.repo_root,
                allowed_local_root=self.temp_root,
            )


if __name__ == "__main__":
    unittest.main()

