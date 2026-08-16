# Cybersecurity Job Radar - Scoring v2.1 Update

This update corrects quality problems found during manual review of the first live v2 handoff. It changes filtering, scoring, gap analysis, age handling and deduplication. It does not change collectors, credentials, application records or CV files.

## What changes

- Explicit fluent, excellent, very good, business-fluent, B2, C1, C2 and native German requirements are rejected for the current A2 profile.
- A company name such as `Deutsche Telekom` no longer creates a German-language warning.
- Vacancies older than 120 days are rejected. Vacancies older than 60 days and vacancies without a reliable date receive score caps.
- `NICE-TO-HAVE` sections propagate to following bullet points, keeping optional skills out of mandatory gaps.
- Missing mandatory infrastructure, cloud, SOC, DLP, EDR, GitHub-security, bug-bounty and OT/ICS requirements are identified more accurately.
- Multiple missing mandatory skills cap a vacancy at 59/100, preserving it only as a stretch candidate.
- Same-company postings with identical or near-identical descriptions are merged even when the title or city differs. Berlin is preferred when source quality is equal.
- Duplicate comparisons are bounded for large boards.
- Offline integration tests use a fixed reference date.

## Files changed

- `config/candidate_profile.json`
- `config/search_config.json`
- `src/analysis.py`
- `src/deduplication.py`
- `src/filters.py`
- `src/main.py`
- `src/reporting.py`
- `src/scoring.py`
- `tests/test_analysis.py`
- `tests/test_filters_and_scoring.py`
- `tests/test_integration.py`
- `tests/test_normalize_and_dedupe.py`
- `README.md`
- `VERSION_2_1_UPDATE.md`

## Safe Windows installation

The supplied update ZIP contains `APPLY_UPDATE.ps1`. It stops if the target repository has uncommitted changes, creates a backup outside the repository, copies only the changed files and runs the complete test suite.

```powershell
Set-Location C:\JCR
Expand-Archive -Path .\Cybersecurity_Job_Radar_v2_1_Update.zip -DestinationPath .\Cybersecurity_Job_Radar_v2_1_Update -Force
Set-Location .\Cybersecurity_Job_Radar_v2_1_Update
PowerShell -ExecutionPolicy Bypass -File .\APPLY_UPDATE.ps1
```

The default target is:

```text
C:\JCR\Cybersecurity_Job_Radar_v1
```

To use another target:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\APPLY_UPDATE.ps1 -TargetRepo "C:\path\to\your\repo"
```

## Commit and push

Only continue when the installer reports that all tests passed.

```powershell
Set-Location C:\JCR\Cybersecurity_Job_Radar_v1
git status
git add config\candidate_profile.json config\search_config.json src\analysis.py src\deduplication.py src\filters.py src\main.py src\reporting.py src\scoring.py tests\test_analysis.py tests\test_filters_and_scoring.py tests\test_integration.py tests\test_normalize_and_dedupe.py README.md VERSION_2_1_UPDATE.md
git diff --cached --stat
git commit -m "fix: improve language age gap and duplicate scoring"
git pull --rebase origin main
git push origin main
```

Run **Actions -> Daily Cybersecurity Job Radar -> Run workflow** once. A correct live result should no longer rank old Scalian vacancies or roles demanding fluent/C1 German, and Qdrant should not contain a false German-language warning.

## Rollback

The installer prints the backup folder it created. If necessary, copy the backed-up files from that folder back to the repository, run the tests, and commit the rollback. The update never overwrites files in `data/` or `reports/archive/`.
