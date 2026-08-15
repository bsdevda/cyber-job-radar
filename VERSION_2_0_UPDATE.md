# Cybersecurity Job Radar Version 2.0 Update

## What this update delivers

Version 2.0 completes roadmap steps 3-6:

1. Profile and Scoring v2 based on verified professional evidence.
2. One private ChatGPT handoff file.
3. Ashby, Lever, and Personio public collectors.
4. Weekly role-demand, skill-gap, score-band, and application-funnel analytics.

It also adds regression protection for explicit US/UK/Canada restrictions, generic non-cyber titles, physical security, academic jobs, and partial ATS failures.

## Preserve these files

Do not replace or delete:

- `data/jobs.json`
- `data/seen_jobs.json`
- `data/job_history.json`
- `data/applications.json`
- `reports/archive/`

They contain your accumulated state. The first v2 run safely creates or refreshes the other generated outputs.

## Install on Windows PowerShell

Place `Cybersecurity_Job_Radar_v2_Update.zip` in `C:\JCR`, then run:

```powershell
Set-Location C:\JCR\Cybersecurity_Job_Radar_v1
git status
```

If the working tree is not clean, commit your intentional edits first. Do not force-push.

Create a recoverable backup outside the Git repository:

```powershell
New-Item -ItemType Directory -Force C:\JCR\v1_1_config_backup | Out-Null
Copy-Item .\config\companies.json C:\JCR\v1_1_config_backup\companies.json
Copy-Item .\config\candidate_profile.json C:\JCR\v1_1_config_backup\candidate_profile.json
```

Extract the update to a temporary folder and copy only the controlled update paths:

```powershell
$UpdateRoot = "C:\JCR\Cybersecurity_Job_Radar_v2_Update"
if (Test-Path $UpdateRoot) { Remove-Item $UpdateRoot -Recurse -Force }
Expand-Archive -Path "C:\JCR\Cybersecurity_Job_Radar_v2_Update.zip" -DestinationPath $UpdateRoot -Force
Copy-Item "$UpdateRoot\.github" . -Recurse -Force
Copy-Item "$UpdateRoot\config" . -Recurse -Force
Copy-Item "$UpdateRoot\src" . -Recurse -Force
Copy-Item "$UpdateRoot\tests" . -Recurse -Force
Copy-Item "$UpdateRoot\README.md","$UpdateRoot\CHATGPT_ANALYSIS_PROMPT.md","$UpdateRoot\VERSION_2_0_UPDATE.md" . -Force
```

The ZIP deliberately excludes your mutable job/application/history data.

## Validate before committing

```powershell
python -m unittest discover -s tests -v
```

Required checks:

- all tests end in `OK`;
- the end-to-end test explicitly collects fixture jobs from Ashby, Lever, and Personio;
- the handoff and weekly-output integration assertions pass.

The live workflow can take several minutes because it checks many employer boards. Keep the local code-update commit separate from generated job-data changes.

## Commit safely

Review before staging:

```powershell
git status
git diff --stat
```

Stage only the code/configuration update; the workflow will commit generated outputs separately:

```powershell
git add .github config src tests README.md CHATGPT_ANALYSIS_PROMPT.md VERSION_2_0_UPDATE.md
git status
git commit -m "feat: add profile scoring v2 and expanded ATS analytics"
git pull --rebase origin main
git push
```

The LF-to-CRLF warning on Windows is informational. Do not use `git add .` if a PDF, DOCX, CV, credential, or unrelated file appears in `git status`.

## Verify GitHub Actions

1. Open **Actions** in the repository.
2. Select **Daily Cybersecurity Job Radar**.
3. Run the workflow on `main`.
4. Confirm tests, collection, and the commit step are green.
5. Open `data/source_health.json` and verify Arbeitnow, Remotive, Greenhouse, Ashby, Lever, and Personio are listed.
6. Confirm `reports/latest.md` contains **TOP MATCHES**, **REVIEW NEXT**, and **Source Health**.
7. Confirm `reports/chatgpt_handoff.json` contains `candidate_profile`, `jobs`, and `analysis_request`.
8. Confirm `data/weekly_analytics.json` has a latest snapshot and `reports/weekly.md` has skill-gap and funnel sections.
9. Synchronize the local PC after the workflow's bot commit:

```powershell
git pull --rebase origin main
```

## Daily use

1. Read the top ten in `reports/latest.md`.
2. Upload only `reports/chatgpt_handoff.json` for detailed private analysis.
3. Record every submitted application and outcome in `data/applications.json`.
4. Review `reports/weekly.md` once per week before choosing the next skill-development priority.
