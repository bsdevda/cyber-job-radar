# Cybersecurity Job Radar - Selective Alerts and Quality Calibration v2.3

This update adds a free high-signal GitHub notification and an evidence-based rolling 14-daily-run review. It does not add paid services, external notification credentials, automated applications, or automatic scoring changes.

## Notification behavior

One GitHub Issue is created when a run contains at least one vacancy that is all of the following:

- newly discovered (`NEW`);
- not already tracked as applied/rejected/interviewed/etc.;
- scored at least 80;
- therefore recommended `APPLY FIRST` at 85+ or strong `APPLY` at 80-84.

One Issue contains up to ten qualifying jobs. Its title contains a stable digest of the included job keys, and the workflow checks existing Issue titles before creating it. Workflow retries therefore do not intentionally send the same alert twice.

The workflow uses GitHub's built-in token with only `contents: write` and `issues: write`. The GitHub CLI reads the body from `reports/job_alert.md`; vacancy text is never executed as shell syntax. If Issue creation is unavailable, that step reports a warning without blocking collection and report commits.

After installation, enable repository Issues and use **Watch → Custom → Issues** to receive GitHub web/email notifications.

## Fourteen-run quality review

`reports/quality_review.md` covers the latest 14 calendar days containing a v2.3 run whose `employer_mode` is `daily`. Preserved older history is not counted. Only the final rerun on a date counts. Sunday/manual `full` scans are excluded because their coverage is different.

Automatically measured:

- relevant job observations and newly relevant jobs;
- duplicates and duplicate rate;
- source checks, failures, partials, and failure rate;
- average workflow duration beginning before dependency installation/tests;
- applications submitted and interviews received;
- application/interview performance by score band.

Manually supplied:

- suitable versus false-positive radar jobs;
- suitable vacancies found outside the radar.

The report refuses premature tuning. It requires 14 daily runs, at least five manually reviewed jobs for a minimally meaningful false-positive rate, and at least six usable application outcomes containing both interviews and negative outcomes before comparing score components. It never edits scoring weights.

## Feedback commands

```powershell
python -m src.quality_review mark --job-key "PASTE_JOB_KEY" --verdict suitable --notes "Verified fit"
python -m src.quality_review mark --job-key "PASTE_JOB_KEY" --verdict false-positive --notes "Reason"
python -m src.quality_review missed --company "Example GmbH" --position "Security Tester" --url "https://example.com/job" --found-date "2026-08-17" --reason "Source not covered"
python -m src.quality_review list
python -m src.quality_review report
```

## Files changed

- `.github/workflows/daily-jobs.yml`
- `config/search_config.json`
- `src/main.py`
- `src/notifications.py`
- `src/quality_review.py`
- `tests/test_integration.py`
- `tests/test_notifications.py`
- `tests/test_quality_review.py`
- `README.md`
- `VERSION_2_3_UPDATE.md`

The installer creates initial `data/quality_feedback.json`, `reports/job_alert.json`, `reports/job_alert.md`, `reports/quality_review.json`, and `reports/quality_review.md` only when missing. It never overwrites existing feedback, applications, job history, company health, or archives.

## Safe Windows installation

```powershell
Set-Location C:\JCR
Expand-Archive -Path .\Cybersecurity_Job_Radar_v2_3_Update.zip `
  -DestinationPath .\Cybersecurity_Job_Radar_v2_3_Update -Force
Set-Location .\Cybersecurity_Job_Radar_v2_3_Update
PowerShell -ExecutionPolicy Bypass -File .\APPLY_UPDATE.ps1
```

The default target is `C:\JCR\Cybersecurity_Job_Radar_v1`. The installer requires a clean Git worktree, verifies packaged checksums, backs up replaced files, and rolls back if the complete test suite fails.

## Commit and push

```powershell
Set-Location C:\JCR\Cybersecurity_Job_Radar_v1
git status
git add .github config src tests README.md VERSION_2_3_UPDATE.md data\quality_feedback.json reports\job_alert.json reports\job_alert.md reports\quality_review.json reports\quality_review.md
git diff --cached --stat
git commit -m "feat: add selective job alerts and quality calibration"
git pull --rebase origin main
git push origin main
```

Run a manual `daily` workflow. Confirm the workflow passes, generated reports are committed, and no Issue is created unless a `NEW` job scores at least 80. Then enable **Watch → Custom → Issues**.

## Privacy

Application and quality-feedback notes committed to a public repository are public. Store only short professional reasons; never include recruiter contact details, private messages, visa documents, or CV files.
