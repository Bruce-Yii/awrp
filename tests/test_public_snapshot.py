from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ALLOWED_TOP_LEVEL = {
    ".gitattributes",
    ".gitignore",
    ".github",
    "AGENTS.md",
    "AWRP-BOOTSTRAP.md",
    "LICENSE",
    "README.md",
    "bridge",
    "docs",
    "examples",
    "protocol",
    "schemas",
    "templates",
    "tests",
    "tools",
}

FORBIDDEN_PATH_PARTS = {
    ".awrp",
    "bridge/requests",
    "channels",
    "contexts",
    "incidents",
    "projects",
    "relay.json",
    "tasks",
}

IGNORED_TOP_LEVEL = {
    ".coverage",
    ".demo",
    ".pytest_cache",
    "__pycache__",
    "data",
    "htmlcov",
    "releases",
    "scripts",
    "temp",
}

SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "github_pat": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "provider_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

PRIVATE_MARKERS = {
    "windows_user_path": re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE),
    "workspace_path": re.compile(r"[A-Za-z]:\\12412\\", re.IGNORECASE),
    "personal_resume": re.compile(r"\b(?:personal resume|candidate resume|简历)\b", re.IGNORECASE),
    "candidate_profile": re.compile(r"\b(?:candidate profile|候选人画像|求职画像)\b", re.IGNORECASE),
    "private_relay_identity": re.compile(r"Bruce-Yii/agent-relay"),
    "internal_project_name": re.compile(
        r"\b(?:modelscope|openclaw|evalscope|pilotdeck|cherry|funasr|ragflow|weknora|laya|dify|n8n|qdrant|teamai|sillytavern|airi)\b",
        re.IGNORECASE,
    ),
}


def public_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        result = None
    if result is not None and result.stdout:
        return [ROOT / relative for relative in result.stdout.decode("utf-8").split("\0") if relative]
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and not any(part in IGNORED_TOP_LEVEL or part == "__pycache__" for part in path.parts)
    ]


class PublicSnapshotTest(unittest.TestCase):
    def test_only_public_safe_top_level_paths(self) -> None:
        actual = {path.relative_to(ROOT).parts[0] for path in public_files()}
        self.assertEqual(actual, ALLOWED_TOP_LEVEL)

    def test_private_relay_state_is_absent(self) -> None:
        for path in public_files():
            relative = path.relative_to(ROOT).as_posix()
            for forbidden in FORBIDDEN_PATH_PARTS:
                self.assertFalse(
                    relative == forbidden or relative.startswith(forbidden + "/"),
                    msg=f"private relay path leaked into public snapshot: {relative}",
                )

    def test_text_files_contain_no_high_confidence_secrets(self) -> None:
        for path in public_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for name, pattern in SECRET_PATTERNS.items():
                self.assertIsNone(pattern.search(text), msg=f"{name} in {path.relative_to(ROOT)}")

    def test_text_files_contain_no_private_markers(self) -> None:
        for path in public_files():
            if path.resolve() == Path(__file__).resolve():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for name, pattern in PRIVATE_MARKERS.items():
                self.assertIsNone(pattern.search(text), msg=f"{name} in {path.relative_to(ROOT)}")

    def test_natural_source_volume_reaches_ghfind_full_size_bucket(self) -> None:
        # Measure the exact Git blobs that will be published. Working-tree byte
        # counts are platform-dependent because Windows checkouts can expand LF
        # to CRLF even when the canonical blob is unchanged.
        source_bytes = 0
        for path in public_files():
            relative = path.relative_to(ROOT).as_posix()
            result = subprocess.run(
                ["git", "-C", str(ROOT), "cat-file", "-s", f":{relative}"],
                capture_output=True,
            )
            source_bytes += int(result.stdout) if result.returncode == 0 else path.stat().st_size
        self.assertGreaterEqual(source_bytes, 1_000_000)

    def test_readme_is_a_substantive_product_document(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        meaningful = re.sub(r"\s+", " ", readme).strip()
        self.assertGreaterEqual(len(meaningful), 800)
        for signal in ("Quick start", "Tests", "Features", "Architecture", "python tools/awrp.py"):
            self.assertIn(signal, readme)


if __name__ == "__main__":
    unittest.main()
