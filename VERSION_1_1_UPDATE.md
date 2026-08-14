# Cybersecurity Job Radar Version 1.1 Update

## Repository assessment

The Version 1 code already had the correct incremental shape: isolated collector classes, one normalization/filter/scoring pipeline, atomic JSON storage, persistent history, and one reporting system. Version 1.1 therefore extends those components and does not rebuild Arbeitnow, Remotive, scoring, filters, or storage.

## Version 1.1 architecture

```text
Arbeitnow ────┐
Remotive ─────┼─> normalize ─> deduplicate ─> filter ─> score ─> history ─> reports
Greenhouse ───┘                          └───────────────────────> source health
```

Greenhouse employers are read from `config/companies.json` and queried sequentially through the public Job Board API. One employer failure produces a partial source result; it does not discard successful employers or stop the general sources. Invalid configuration and total operational-source failure produce a non-zero command exit.

## Files created

- `src/collectors/greenhouse.py`
- `src/config_validation.py`
- `src/source_health.py`
- `data/source_health.json`
- `tests/fixtures/greenhouse.json`
- `tests/test_greenhouse.py`
- `tests/test_config_validation.py`
- `tests/test_source_health.py`
- `VERSION_1_1_UPDATE.md`

## Files modified

- `.github/workflows/daily-jobs.yml`
- `README.md`
- `config/companies.json`
- `config/sources.json`
- `src/__init__.py`
- `src/collectors/__init__.py`
- `src/collectors/base.py`
- `src/deduplication.py`
- `src/main.py`
- `src/normalize.py`
- `src/reporting.py`
- `tests/test_integration.py`
- `tests/test_normalize_and_dedupe.py`

The update archive deliberately excludes `data/jobs.json`, `data/seen_jobs.json`, `data/job_history.json`, `data/applications.json`, and existing reports. Extracting it over Version 1 cannot replace those files.

## Greenhouse configuration

Add real employers to the `greenhouse` array. For `https://boards.greenhouse.io/example`, use `example` as the board token:

```json
{
  "priority_companies": [],
  "greenhouse": [
    {
      "name": "Example GmbH",
      "board": "example",
      "priority": false,
      "enabled": true,
      "notes": "Optional"
    }
  ],
  "lever": [],
  "ashby": [],
  "recruitee": [],
  "smartrecruiters": []
}
```

Do not guess board tokens. Verify them on the employer's genuine Greenhouse careers URL. Setting `enabled` to `false` keeps an entry without querying it. `priority` is reported separately and never changes the candidate-fit score.

## Install the update in Windows PowerShell

Run these commands from the existing repository folder. First preserve any intended local edit:

```powershell
git status
git add tests\test_integration.py
git commit -m "test: isolate integration data from stored jobs"
git pull --rebase origin main
```

If Git reports that there is nothing to commit, continue. If another file is modified, review it before adding it. Do not use a force push.

Place `CyberJobRadar_v1_1_Update.zip` in Downloads, then extract it over the repository:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\CyberJobRadar_v1_1_Update.zip" -DestinationPath . -Force
python -m unittest discover -s tests -v
```

Expected result:

```text
Ran 28 tests
OK
```

Commit only the update paths, not refreshed live job data:

```powershell
git add .github config README.md VERSION_1_1_UPDATE.md src tests data\source_health.json
git status
git commit -m "feat: add Greenhouse collector and source health"
git push origin main
```

## GitHub Actions verification

1. Open the repository on GitHub.
2. Open **Actions** and select **Daily Cybersecurity Job Radar**.
3. Select **Run workflow**, choose `main`, and run it.
4. Verify that checkout, Python setup, tests, collection, and commit are green.
5. Confirm `data/source_health.json`, `reports/latest.json`, and `reports/latest.md` were updated.
6. In `reports/latest.md`, confirm the **Source Health** section shows Greenhouse as idle, OK, partial, or failed with a clear count.
7. If the workflow created a bot commit, synchronize the PC before the next local edit:

```powershell
git pull --rebase origin main
```

Version 1.2 (Lever and Ashby) should begin only after this Version 1.1 workflow is green.
