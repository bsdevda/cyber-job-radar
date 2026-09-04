# Cybersecurity Job Radar v2.5

## Exact eligibility policy

The radar now uses a strict allowlist rather than treating every German city or every generic remote label as eligible.

| Vacancy location and model | Result |
| --- | --- |
| Berlin on-site | Accept |
| Berlin hybrid | Accept |
| Berlin remote | Accept |
| Germany outside Berlin, fully remote | Accept |
| Germany outside Berlin, on-site or hybrid | Reject |
| Europe, EU, EEA or EMEA remote | Accept and flag Germany-employment verification |
| Worldwide, anywhere or work-from-anywhere remote | Accept and flag Germany-employment verification |
| Remote with no permitted country/region stated | Reject |
| Explicit US/UK/Canada/other non-target location with generic global company wording | Reject |

Europe and worldwide entries stay visible because they match the requested search scope, but their report warning tells the user to confirm that the employer can hire a person working from Germany.

## English-speaking profile policy

The target is an English-speaking security role. The radar accepts optional German and mandatory A1/A2 requirements because the verified profile is A2. It rejects:

- mandatory B1, B2, C1, C2, fluent, advanced or native German;
- mandatory German when the required level is not stated; and
- vacancy text that is predominantly German.

This does not change the stored profile to B1. It remains A2 and currently studying toward B1.

## Existing job cleanup

Every cumulative job is rechecked against the current location and language policy before `reports/latest.md` and `reports/chatgpt_handoff.json` are built. An old Munich or unclear-remote job can remain in historical JSON for audit purposes but receives `policy_excluded: true` and cannot return to the application queue.

## Notifications and operation

The existing GitHub Actions schedule remains the always-on runner. A new, unapplied score-80+ match creates one deduplicated GitHub Issue. Watching repository Issues can produce GitHub web, mobile-app and email notifications without another service.

Telegram is technically possible with a bot token and chat ID, and direct email is possible with an email provider credential. Neither credential is added by this location-policy update. Do not commit either value to the repository; store it only as a GitHub Actions secret.

## Validation

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected result:

```text
Ran 71 tests
OK
```

The tests cover all accepted scopes, non-Berlin German on-site/hybrid rejection, unclear-remote rejection, restricted-region precedence, A2/B1 language boundaries, German-text rejection, stored-job revalidation, report exclusion and LinkedIn worldwide inference.
