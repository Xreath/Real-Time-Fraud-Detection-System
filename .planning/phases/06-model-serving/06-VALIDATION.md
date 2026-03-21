---
phase: 6
slug: model-serving
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (not yet configured — Wave 0 installs) |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `pytest tests/test_pyfunc.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_pyfunc.py -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | SERV-01 | integration | `pytest tests/test_serving.py::test_invocations -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | SERV-02 | smoke | `pytest tests/test_serving.py::test_health_check -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | SERV-03 | integration | `pytest tests/test_serving.py::test_no_skew -x` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 1 | SERV-04 | unit | `pytest tests/test_pyfunc.py::test_champion_alias_loaded -x` | ❌ W0 | ⬜ pending |
| 06-01-05 | 01 | 1 | SERV-05 | smoke | `docker compose ps fraud-api` | N/A — manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pyfunc.py` — unit tests for FraudPyfunc class (no server needed): preprocessing logic, threshold env var, feature column order
- [ ] `tests/test_serving.py` — integration tests requiring running `fraud-api` container: /health, /invocations, skew check
- [ ] `tests/conftest.py` — shared fixtures (sample transaction DataFrame, expected score ranges)
- [ ] Framework install: `uv pip install pytest` if not already in requirements.txt

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `fraud-api` starts with `docker compose up` | SERV-05 | Requires full Docker stack | Run `docker compose up -d` and verify `docker compose ps fraud-api` shows healthy |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
