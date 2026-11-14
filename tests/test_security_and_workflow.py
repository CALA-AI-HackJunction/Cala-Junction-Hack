"""CRACI CI/CD workflow, network egress lockdown, secret hygiene, and dataset integrity tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Complete set of 24 official CRACI built-in presets from https://docs.craci.com/guides/setup-action-network/
VALID_CRACI_PRESETS = frozenset({
    "pypi",
    "npm",
    "rubygems",
    "alpine",
    "debian",
    "ubuntu",
    "cargo",
    "golang",
    "fonts",
    "cache-nixos-org",
    "dockerhub",
    "ghcr",
    "quay",
    "gcr",
    "ecr-public",
    "github",
    "gitlab",
    "docker-apt",
    "nodesource",
    "raspbian",
    "yocto",
    "openembedded",
    "bitbucket",
    "googlesource",
})

# CRACI-managed CA environment variables that workflows must never overwrite (per craci_skill.md)
CRACI_MANAGED_CA_VARS = frozenset({
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NIX_SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    "JAVA_TOOL_OPTIONS",
})


def _strip_yaml_comment(line: str) -> str:
    """Strip trailing `# ...` YAML comments outside single/double quotes."""
    in_single = False
    in_double = False
    for idx, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if idx == 0 or line[idx - 1].isspace():
                return line[:idx].rstrip()
    return line.rstrip()


def _parse_scalar(raw: str) -> Any:
    val = raw.strip()
    if val == "":
        return None
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in inner.split(",")]
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    lowered = val.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", val):
        return int(val)
    return val


def _parse_yaml_subset(text: str) -> dict[str, Any]:
    """Parse GitHub Actions YAML using PyYAML if installed, or a strict stdlib indentation parser."""
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        leading = raw_line[: len(raw_line) - len(raw_line.lstrip(" \t"))]
        if "\t" in leading:
            raise ValueError(f"Invalid YAML tab indentation at line {lineno}")

    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        if not isinstance(loaded, dict):
            raise ValueError("Top-level workflow YAML must be a mapping")
        return loaded
    except ModuleNotFoundError:
        pass

    lines = text.splitlines()
    total = len(lines)

    def next_meaningful(idx: int) -> tuple[int, int, str] | None:
        while idx < total:
            raw = lines[idx]
            cleaned = _strip_yaml_comment(raw)
            if cleaned.strip():
                indent = len(cleaned) - len(cleaned.lstrip(" "))
                return idx, indent, cleaned.strip()
            idx += 1
        return None

    def parse_block_scalar(start_idx: int, parent_indent: int) -> tuple[str, int]:
        collected: list[str] = []
        block_indent: int | None = None
        idx = start_idx
        while idx < total:
            raw = lines[idx]
            if not raw.strip():
                collected.append("")
                idx += 1
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            if indent <= parent_indent:
                break
            if block_indent is None:
                block_indent = indent
            collected.append(raw[block_indent:])
            idx += 1
        while collected and collected[-1] == "":
            collected.pop()
        return "\n".join(collected) + ("\n" if collected else ""), idx

    def parse_node(idx: int, expected_indent: int) -> tuple[Any, int]:
        peek = next_meaningful(idx)
        if peek is None or peek[1] < expected_indent:
            return None, idx
        _, first_indent, first_content = peek
        if first_content.startswith("- ") or first_content == "-":
            return parse_sequence(peek[0], first_indent)
        return parse_mapping(peek[0], first_indent)

    def parse_mapping(idx: int, map_indent: int) -> tuple[dict[str, Any], int]:
        mapping: dict[str, Any] = {}
        while True:
            peek = next_meaningful(idx)
            if peek is None:
                break
            line_idx, indent, content = peek
            if indent < map_indent or content.startswith("- ") or content == "-":
                break
            if indent > map_indent:
                raise ValueError(f"Unexpected mapping indentation at line {line_idx + 1}: {content}")
            if ":" not in content:
                raise ValueError(f"Expected key: value at line {line_idx + 1}: {content}")
            key_part, val_part = content.split(":", 1)
            key = str(_parse_scalar(key_part))
            val_str = val_part.strip()
            if val_str in ("|", "|-", ">", ">-"):
                block_text, idx = parse_block_scalar(line_idx + 1, indent)
                mapping[key] = block_text
            elif val_str == "":
                child, idx = parse_node(line_idx + 1, indent + 1)
                mapping[key] = child
            else:
                mapping[key] = _parse_scalar(val_str)
                idx = line_idx + 1
        return mapping, idx

    def parse_sequence(idx: int, seq_indent: int) -> tuple[list[Any], int]:
        items: list[Any] = []
        while True:
            peek = next_meaningful(idx)
            if peek is None:
                break
            line_idx, indent, content = peek
            if indent < seq_indent or not (content == "-" or content.startswith("- ")):
                break
            if indent > seq_indent:
                raise ValueError(f"Unexpected sequence indentation at line {line_idx + 1}: {content}")
            rest = content[1:].strip()
            if not rest:
                child, idx = parse_node(line_idx + 1, indent + 1)
                items.append(child)
            elif ":" in rest and not (rest.startswith('"') or rest.startswith("'")):
                item_indent = indent + 2
                key_part, val_part = rest.split(":", 1)
                key = str(_parse_scalar(key_part))
                val_str = val_part.strip()
                item_map: dict[str, Any] = {}
                if val_str in ("|", "|-", ">", ">-"):
                    block_text, next_idx = parse_block_scalar(line_idx + 1, indent)
                    item_map[key] = block_text
                elif val_str == "":
                    child, next_idx = parse_node(line_idx + 1, item_indent + 1)
                    item_map[key] = child
                else:
                    item_map[key] = _parse_scalar(val_str)
                    next_idx = line_idx + 1
                more_peek = next_meaningful(next_idx)
                if more_peek is not None and more_peek[1] == item_indent and not more_peek[2].startswith("-"):
                    extra_map, next_idx = parse_mapping(next_idx, item_indent)
                    item_map.update(extra_map)
                items.append(item_map)
                idx = next_idx
            else:
                items.append(_parse_scalar(rest))
                idx = line_idx + 1
        return items, idx

    parsed, _ = parse_mapping(0, 0)
    return parsed


class CraciWorkflowPolicyTests(unittest.TestCase):
    """Validate `.github/workflows/ci.yml` against official CRACI Runner & Network specs."""

    def setUp(self) -> None:
        self.assertTrue(WORKFLOW_PATH.is_file(), f"Missing CI workflow at {WORKFLOW_PATH}")
        self.raw_yaml = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.workflow = _parse_yaml_subset(self.raw_yaml)

    def test_workflow_parses_cleanly_and_uses_craci_runner(self) -> None:
        self.assertIn("jobs", self.workflow)
        jobs = self.workflow["jobs"]
        self.assertIsInstance(jobs, dict)
        self.assertGreaterEqual(len(jobs), 1)

        for job_id, job in jobs.items():
            runs_on = job.get("runs-on")
            if isinstance(runs_on, list):
                self.assertEqual(runs_on, ["craci"], f"Job {job_id} must route strictly to 'craci'")
            else:
                self.assertEqual(runs_on, "craci", f"Job {job_id} must set `runs-on: craci`")

    def test_craci_setup_step_enforces_size_and_deny_unmatched_egress_policy(self) -> None:
        job = self.workflow["jobs"]["verify-and-sbom"]
        steps = job.get("steps", [])
        self.assertGreaterEqual(len(steps), 9, "Expected full 9-step hardened CI pipeline")

        setup_step = steps[0]
        self.assertEqual(
            setup_step.get("uses"),
            "cracicorp/setup@v1",
            "First step must be `cracicorp/setup@v1` per CRACI runner workflow convention",
        )
        with_cfg = setup_step.get("with", {})
        self.assertIsInstance(with_cfg, dict)

        # CRACI requires numeric size; non-numeric discards the setup step
        size_val = str(with_cfg.get("size", ""))
        self.assertTrue(size_val.isdigit() and int(size_val) == 4, f"Expected size '4', got {size_val!r}")
        self.assertIn('size: "4"', self.raw_yaml)

        network_raw = with_cfg.get("network")
        self.assertIsInstance(network_raw, str)
        network_policy = _parse_yaml_subset(network_raw)

        self.assertEqual(
            network_policy.get("default"),
            "deny",
            "CRACI egress policy must set `default: deny` for complete SBOM attestation & exfiltration defense",
        )
        presets = network_policy.get("presets")
        self.assertEqual(presets, ["pypi", "github"])
        self.assertTrue(
            set(presets).issubset(VALID_CRACI_PRESETS),
            f"Unknown CRACI network presets: {set(presets) - VALID_CRACI_PRESETS}",
        )
        unknown_net_keys = set(network_policy.keys()) - {"default", "presets", "sources", "connections"}
        self.assertEqual(unknown_net_keys, set(), f"CRACI rejects unknown network keys: {unknown_net_keys}")

    def test_workflow_preserves_craci_managed_ca_bundle_variables(self) -> None:
        top_env = self.workflow.get("env") or {}
        self.assertTrue(CRACI_MANAGED_CA_VARS.isdisjoint(top_env.keys()))
        for job in self.workflow["jobs"].values():
            job_env = job.get("env") or {}
            self.assertTrue(
                CRACI_MANAGED_CA_VARS.isdisjoint(job_env.keys()),
                f"Workflow must not overwrite CRACI CA trust variables: {CRACI_MANAGED_CA_VARS & set(job_env.keys())}",
            )
            for step in job.get("steps", []):
                step_env = step.get("env") or {}
                self.assertTrue(CRACI_MANAGED_CA_VARS.isdisjoint(step_env.keys()))

    def test_workflow_covers_all_required_pipeline_stages_and_least_privilege(self) -> None:
        permissions = self.workflow.get("permissions", {})
        self.assertEqual(permissions.get("contents"), "read")

        steps = self.workflow["jobs"]["verify-and-sbom"]["steps"]
        uses_list = [s.get("uses") for s in steps if s.get("uses")]
        run_scripts = "\n".join(str(s.get("run", "")) for s in steps if s.get("run"))

        self.assertIn("cracicorp/setup@v1", uses_list)
        self.assertIn("actions/checkout@v4", uses_list)
        self.assertIn("astral-sh/setup-uv@v4", uses_list)
        self.assertIn("actions/upload-artifact@v4", uses_list)

        self.assertIn("uv sync --frozen || uv sync", run_scripts)
        self.assertIn("backend/data/input_manifest.json", run_scripts)
        self.assertIn("uv run python -m backend.cli build", run_scripts)
        self.assertIn("uv run pytest -v", run_scripts)
        self.assertIn("frontend/index.html", run_scripts)


class SecurityAndSecretHygieneTests(unittest.TestCase):
    """Verify `.gitignore` protections, zero leaked credentials, and SHA-256 dataset integrity."""

    SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("Google / Gemini API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
        ("OpenAI / Featherless sk- secret key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
        ("GitHub Personal Access Token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
        ("Aiven credential URI", re.compile(r"\b(?:postgres(?:ql)?|valkeys?|rediss?)://[^/\s:@]+:[^@\s]{8,}@")),
        ("Private cryptographic key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
        (
            "Hardcoded secret env assignment",
            re.compile(
                r"^[ \t]*(?:export[ \t]+)?(?:CALA_API_KEY|GEMINI_API_KEY|GEMMA_API_KEY|FEATHERLESS_API_KEY|CRACI_API_TOKEN|AIVEN_PG_URI|AIVEN_VALKEY_URL)[ \t]*=[ \t]*['\"]?[A-Za-z0-9_:/@.-]{12,}",
                re.MULTILINE,
            ),
        ),
    )

    def test_gitignore_protects_env_secrets_sqlite_and_generated_snapshot(self) -> None:
        gitignore_path = REPO_ROOT / ".gitignore"
        self.assertTrue(gitignore_path.is_file(), "Missing .gitignore at repository root")
        rules = {
            line.strip()
            for line in gitignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        self.assertIn(".env", rules)
        self.assertIn(".env.*", rules)
        self.assertIn("!.env.example", rules)
        self.assertIn("*.sqlite3", rules)
        self.assertIn("backend/data/snapshot.json", rules)

        if (REPO_ROOT / ".git").exists():
            for ignored_sample in (".env", ".env.local", "backend/data/analyses.sqlite3", "backend/data/snapshot.json"):
                proc = subprocess.run(
                    ["git", "check-ignore", "-q", ignored_sample],
                    cwd=REPO_ROOT,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, f"Expected git to ignore {ignored_sample}")

            example_proc = subprocess.run(
                ["git", "check-ignore", "-q", ".env.example"],
                cwd=REPO_ROOT,
                check=False,
            )
            self.assertNotEqual(example_proc.returncode, 0, ".env.example must remain trackable")

    def test_env_example_has_empty_placeholders_only(self) -> None:
        env_example = REPO_ROOT / ".env.example"
        self.assertTrue(env_example.is_file(), "Missing .env.example")
        content = env_example.read_text(encoding="utf-8")

        sensitive_vars = {
            "CALA_API_KEY",
            "GEMINI_API_KEY",
            "GEMMA_API_KEY",
            "FEATHERLESS_API_KEY",
            "AIVEN_PG_URI",
            "AIVEN_VALKEY_URL",
            "CRACI_API_TOKEN",
        }
        found_vars: set[str] = set()
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in sensitive_vars:
                found_vars.add(key)
                self.assertEqual(value, "", f"{key} in .env.example must be blank, got {value!r}")

        self.assertEqual(found_vars, sensitive_vars)

    def test_zero_secrets_in_tracked_and_workspace_source_files(self) -> None:
        candidate_files: set[Path] = set()

        if (REPO_ROOT / ".git").exists():
            out = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT, text=True)
            for rel in out.splitlines():
                p = REPO_ROOT / rel
                if p.is_file():
                    candidate_files.add(p)

        for folder in (".github", "tests", "docs", "scripts", "backend", "frontend"):
            base = REPO_ROOT / folder
            if not base.is_dir():
                continue
            for p in base.rglob("*"):
                if p.is_file() and "__pycache__" not in p.parts:
                    candidate_files.add(p)

        skip_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".sqlite3", ".pyc"}
        violations: list[str] = []

        for file_path in sorted(candidate_files):
            rel_parts = file_path.relative_to(REPO_ROOT).parts
            if file_path.name == ".env" or file_path.name.startswith(".env.") and file_path.name != ".env.example":
                continue
            if file_path.suffix.lower() in skip_suffixes:
                continue
            if rel_parts[:2] == ("backend", "data") and file_path.suffix == ".json":
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for label, pattern in self.SECRET_PATTERNS:
                match = pattern.search(text)
                if match:
                    violations.append(f"{file_path.relative_to(REPO_ROOT)}: {label}")

        self.assertEqual(violations, [], f"Detected potential secret leakage: {violations}")

    def test_input_manifest_sha256_digests_match_canonical_datasets(self) -> None:
        manifest_path = REPO_ROOT / "backend" / "data" / "input_manifest.json"
        self.assertTrue(manifest_path.is_file(), "Missing backend/data/input_manifest.json")
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 3)

        for entry in entries:
            rel = entry["packaged_filename"]
            dataset_path = REPO_ROOT / "backend" / rel
            if not dataset_path.is_file():
                dataset_path = REPO_ROOT / "backend" / "data" / Path(rel).name
            self.assertTrue(dataset_path.is_file(), f"Missing canonical dataset {rel}")
            self.assertEqual(dataset_path.stat().st_size, entry["size_bytes"])
            digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
            self.assertEqual(digest, entry["sha256"])


if __name__ == "__main__":
    unittest.main()
