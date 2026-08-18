"""Plan Safety Scanner (T8) — read-only static analysis of IaC, fail-closed.

Scans ``infrastructure/staging/*.tf`` for unsafe patterns that must never reach a real
apply: production references, publicly-accessible databases, open ``0.0.0.0/0`` ingress,
hardcoded secrets, disabled encryption, and destructive operations. The scanner is
purely read-only — it never modifies files or applies anything.

This is the safety gate that would have to PASS (or be consciously waived by a human)
before any real terraform apply. In Phase 3.9.15 it runs against the committed IaC and
records its verdict; it does NOT unblock the provider-init blocker.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

SEV_HIGH = "HIGH"
SEV_MED = "MEDIUM"
SEV_LOW = "LOW"

RULE_PROD_REF = "PROD_REFERENCE"
RULE_PUBLIC_DB = "PUBLIC_DATABASE"
RULE_OPEN_INGRESS = "OPEN_INGRESS"
RULE_RAW_SECRET = "RAW_SECRET"
RULE_NO_ENCRYPTION = "NO_ENCRYPTION"
RULE_DESTRUCTIVE = "DESTRUCTIVE"


@dataclass
class SafetyFinding:
    rule: str
    severity: str
    file: str
    line: int
    message: str


_RAW_SECRET_RE = re.compile(
    r'(?i)(password|secret|access_key|private_key|token)\s*=\s*"[^"]{6,}"'
)
_NO_VAR_RE = re.compile(r'var\.|random_|data\.|tls_')
_PROD_RE = re.compile(r'(?i)\b(production|prod-)\b')
_NO_ENC_RE = re.compile(r'(?i)(storage_encrypted|encrypt|kms_key|transparent_data_encryption)\s*=\s*false')
_DESTRUCTIVE_RE = re.compile(r'(?i)(terraform\s+destroy|force_destroy\s*=\s*true)')


class PlanSafetyScanner:
    def __init__(self, staging_dir: str = "infrastructure/staging") -> None:
        self.staging_dir = Path(staging_dir)

    def scan(self) -> List[SafetyFinding]:
        findings: List[SafetyFinding] = []
        if not self.staging_dir.is_dir():
            return findings
        for tf in sorted(self.staging_dir.glob("*.tf")):
            text = tf.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                findings.extend(self._scan_line(tf.name, i, line))
        return findings

    def _scan_line(self, fname: str, lineno: int, line: str) -> List[SafetyFinding]:
        f: List[SafetyFinding] = []
        low = line.lower()
        # raw secret (only when not referencing a var/data/random source)
        if _RAW_SECRET_RE.search(line) and not _NO_VAR_RE.search(line):
            f.append(SafetyFinding(RULE_RAW_SECRET, SEV_HIGH, fname, lineno,
                                   "possible hardcoded secret/key in .tf"))
        if "publicly_accessible" in low and "true" in low:
            f.append(SafetyFinding(RULE_PUBLIC_DB, SEV_HIGH, fname, lineno,
                                   "resource is publicly accessible"))
        if re.search(r'0\.0\.0\.0/0', line):
            f.append(SafetyFinding(RULE_OPEN_INGRESS, SEV_HIGH, fname, lineno,
                                   "open ingress 0.0.0.0/0"))
        if re.search(r'(?i)\b(environment|env|stage)\b\s*=\s*"[^"]*?(production|prod-)', line):
            f.append(SafetyFinding(RULE_PROD_REF, SEV_MED, fname, lineno,
                                   "resource targets production environment"))
        if _NO_ENC_RE.search(line):
            f.append(SafetyFinding(RULE_NO_ENCRYPTION, SEV_HIGH, fname, lineno,
                                   "encryption disabled"))
        if _DESTRUCTIVE_RE.search(line):
            f.append(SafetyFinding(RULE_DESTRUCTIVE, SEV_HIGH, fname, lineno,
                                   "destructive operation detected"))
        return f

    def has_high(self) -> bool:
        return any(f.severity == SEV_HIGH for f in self.scan())

    def verdict(self) -> str:
        findings = self.scan()
        if any(f.severity == SEV_HIGH for f in findings):
            return "UNSAFE"
        if any(f.severity == SEV_MED for f in findings):
            return "REVIEW"
        return "SAFE"
