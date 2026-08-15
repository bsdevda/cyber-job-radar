# Cybersecurity Job Radar 2.0.1 Timeout Hotfix

## Cause

The v2 workflow collected more than 20,000 vacancies and ran the full 60-skill description analysis before rejecting unrelated titles. GitHub Actions therefore cancelled the job at the configured 30-minute limit.

## Fix

- Reject non-security titles before language, experience, and skill-description analysis.
- Run the full Profile/Scoring v2 evidence scan only for eligible security vacancies.
- Log normalization, deduplication, filtering, and scoring durations.
- Log progress every 5,000 unique postings.
- Increase the workflow limit from 30 to 45 minutes as a safety margin.
- Add a regression assertion proving that unrelated, region-locked, and overly senior fixture jobs do not receive the expensive skill scan.

The supplied 20,020-posting synthetic load test completed in approximately 3.3 seconds in the validation environment, with only the 20 genuine security titles receiving full skill analysis. All 38 unit and integration tests pass.

## Install from Windows PowerShell

Extract `Cybersecurity_Job_Radar_v2_Timeout_Hotfix.zip` to `C:\JCR\Cybersecurity_Job_Radar_v2_Timeout_Hotfix`, then run from the real repository:

```powershell
Set-Location C:\JCR\Cybersecurity_Job_Radar_v1
$HotfixRoot = "C:\JCR\Cybersecurity_Job_Radar_v2_Timeout_Hotfix"

Copy-Item "$HotfixRoot\.github\workflows\daily-jobs.yml" ".\.github\workflows\daily-jobs.yml" -Force
Copy-Item "$HotfixRoot\src\main.py" ".\src\main.py" -Force
Copy-Item "$HotfixRoot\tests\test_integration.py" ".\tests\test_integration.py" -Force
Copy-Item "$HotfixRoot\HOTFIX_2_0_1.md" . -Force

python -m unittest discover -s tests -v
git status
git add .github\workflows\daily-jobs.yml src\main.py tests\test_integration.py HOTFIX_2_0_1.md
git commit -m "fix: prevent job radar timeout on large vacancy sets"
git pull --rebase origin main
git push origin main
```

Then manually run **Daily Cybersecurity Job Radar** from GitHub Actions. The log should now show phase timings such as `Normalized`, `Deduplicated`, and `Filtered and scored` before the final report commit.
