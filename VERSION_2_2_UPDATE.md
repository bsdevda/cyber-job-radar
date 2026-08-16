# Cybersecurity Job Radar - Production Operations v2.2

This update makes the 200-employer watchlist safe for a 30-minute GitHub Actions budget and adds structured application-outcome tracking. It preserves the zero-cost, public-feed-only design and does not auto-apply to vacancies.

## What changes

- Splits enabled non-priority employers into five deterministic weekday batches while checking priority employers every weekday.
- Adds a Sunday full-watchlist run; Arbeitnow and Remotive continue to run on every schedule.
- Gives employer ATS requests an eight-second timeout and one retry, with bounded parallel workers.
- Persists company-level health in `data/company_health.json`.
- Recovers successful employers immediately, exponentially delays transient failures, and suppresses HTTP 404/410 identifiers for 30 days before retrying.
- Applies the cybersecurity-title filter before expensive normalization and duplicate comparison.
- Adds the public Recruitee feed and a validated 200-employer configuration.
- Adds Berlin startup/scale-up metadata and dated evidence for employers currently advertising security roles.
- Adds a validated application tracker, CSV export, and weekly funnel cohorts by radar recommendation and CV version.
- Extends the offline suite to 54 tests covering rotations, cooldowns, Recruitee mapping, employer metadata, application validation, and analytics.

## Runtime acceptance result

A production-shaped weekday run completed in 132 seconds. It collected 6,204 raw postings, prefiltered 5,993 non-security titles, processed 211 cybersecurity-title candidates, and produced 18 relevant jobs. All seven configured provider groups completed without a provider-level failure. This is the primary acceptance case for the daily workflow; the full Sunday scan remains bounded by the same request limits and 30-minute workflow guard.

## Scheduling model

| Schedule | Employer mode | Purpose |
| --- | --- | --- |
| Monday-Friday 07:30 Europe/Berlin | `daily` | General sources, all priority employers, and one deterministic employer batch |
| Sunday 08:00 Europe/Berlin | `full` | General sources and the complete enabled employer watchlist, except active cooldowns |
| Manual workflow dispatch | `daily` or `full` | Controlled validation or audit |

Every enabled non-priority employer is assigned to exactly one of the five weekday batches. The assignment is stable, so a repository rerun on the same weekday checks the same group.

## Company-health behavior

`reports/company_health.md` shows selected coverage, verified security-hiring employers, and suppressed identifiers. `data/company_health.json` holds the machine-readable state.

- Success resets the consecutive-failure count and removes any cooldown.
- Transient failures use exponential cooldowns from 24 hours up to 168 hours.
- HTTP 404 and 410 are treated as likely invalid/migrated identifiers and retried after 30 days.
- One invalid employer never stops the remaining employers or general sources.

Do not mark an identifier permanently valid merely because its host responds. Review employer career pages periodically because ATS tenants can migrate.

## Application tracker

Record each application with:

- company and position;
- application date;
- radar recommendation and score;
- CV version and whether a cover letter was used;
- current status;
- response, rejection, and interview dates;
- interview stage, final result, job URL, and non-sensitive notes.

Use the command rather than editing JSON manually:

```powershell
python -m src.application_tracker set `
  --job-key "PASTE_JOB_KEY" `
  --status "APPLIED" `
  --cv-version "appsec-v5" `
  --cover-letter-used yes `
  --notes "Applied through the employer career page"
```

The tracker fills company, position, score, recommendation, URL, and application date from the stored radar job. Later calls with the same `job_key` update the record. Run `python -m src.application_tracker list` to review the funnel or `python -m src.application_tracker export` to regenerate the CSV.

Weekly analytics calculate response, interview, and offer rates overall and by recommendation/CV version. These rates only become meaningful after real outcomes are maintained consistently.

## Files installed

- `.github/workflows/daily-jobs.yml`
- `config/companies.json`
- `config/sources.json`
- `src/analytics.py`
- `src/application_tracker.py`
- `src/collectors/__init__.py`
- `src/collectors/ashby.py`
- `src/collectors/base.py`
- `src/collectors/greenhouse.py`
- `src/collectors/lever.py`
- `src/collectors/personio.py`
- `src/collectors/recruitee.py`
- `src/company_schedule.py`
- `src/config_validation.py`
- `src/main.py`
- `src/reporting.py`
- `src/source_health.py`
- `tests/fixtures/recruitee.json`
- `tests/test_analytics.py`
- `tests/test_application_tracker.py`
- `tests/test_ats_collectors.py`
- `tests/test_company_schedule.py`
- `tests/test_config_validation.py`
- `tests/test_integration.py`
- `tests/test_source_health.py`
- `README.md`
- `VERSION_2_2_UPDATE.md`

The installer creates empty initial `data/company_health.json`, `reports/company_health.md`, and `reports/application_tracker.csv` only if they do not already exist. It never replaces existing job history, applications, company health, or report archives.

## Safe Windows installation

Extract the supplied ZIP and run its installer from the extracted folder:

```powershell
Set-Location C:\JCR
Expand-Archive -Path .\Cybersecurity_Job_Radar_v2_2_Update.zip `
  -DestinationPath .\Cybersecurity_Job_Radar_v2_2_Update -Force
Set-Location .\Cybersecurity_Job_Radar_v2_2_Update
PowerShell -ExecutionPolicy Bypass -File .\APPLY_UPDATE.ps1
```

The default target is `C:\JCR\Cybersecurity_Job_Radar_v1`. Supply `-TargetRepo "C:\path\to\repo"` for another location. The installer refuses a dirty working tree, backs up replaced files, copies the update, and rolls back copied files if the 54-test suite fails.

## Commit and push

After the installer reports success:

```powershell
Set-Location C:\JCR\Cybersecurity_Job_Radar_v1
git status
git add .github config src tests README.md VERSION_2_2_UPDATE.md data\company_health.json reports\company_health.md reports\application_tracker.csv
git diff --cached --stat
git commit -m "feat: add runtime-safe employer scans and application tracking"
git pull --rebase origin main
git push origin main
```

Run a manual `daily` workflow first. Confirm all tests pass, total runtime stays comfortably below 30 minutes, `reports/latest.md` contains jobs, and `reports/company_health.md` explains employer coverage. Do not use `full` for repeated debugging; reserve it for the Sunday/manual audit.

## Privacy and cost

No API key, paid job feed, hosted database, or external server is required. Application records committed to a public repository are public, so keep notes non-sensitive or make the repository private. The tracker never stores the CV itself.
