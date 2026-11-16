"""Tests for Security Auditor."""

from __future__ import annotations

from evaluation.security_audit import SecurityAuditor


def test_security_audit_clean_pass() -> None:
    """Verify security audit scans codebase and confirms zero high/critical vulnerabilities."""
    auditor = SecurityAuditor()
    report = auditor.audit()

    assert report.total_files_scanned > 30
    assert report.is_hardened is True
    assert len(report.findings) == 0
    assert len(report.passed_checks) >= 4
