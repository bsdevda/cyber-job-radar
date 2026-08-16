# Cybersecurity Job Radar v2.4

## What this version changes

### 1. LinkedIn post leads without LinkedIn scraping

`linkedin_posts` reads user-authorized RSS/Atom alerts from the optional GitHub secret `LINKEDIN_POST_FEEDS_JSON`. It does not request LinkedIn, log in, reuse cookies, run a browser, scrape profiles, or bypass access controls.

Only alert entries containing:

- a public LinkedIn `/posts/`, `/feed/update/`, or `/pulse/` URL;
- a target cybersecurity-role phrase; and
- an explicit hiring phrase

enter the radar. Every LinkedIn post is clearly labelled as an unverified lead and capped at score 69 until the complete employer vacancy is verified. This prevents incomplete social posts from triggering a strong-match alert.

LinkedIn does not offer a free general API for searching every member's posts. Feed coverage therefore depends on the alert provider and cannot guarantee every post.

### 2. Fifty active jobs in `reports/latest.md`

The configured report size is now 50. The queue is selected from the cumulative active job database rather than only the current rotating employer batch. This makes still-active jobs visible on quieter days.

All displayed jobs retain score, location, role family, gaps, warnings, direct URL and application status. If fewer than 50 active relevant vacancies exist, the report shows the real number and never adds rejected jobs as filler.

### 3. GitHub Actions application-tracker form

The new **Update Application Tracker** workflow accepts a job key and status through GitHub's form. It:

1. validates the job and dates;
2. enriches it from `data/jobs.json`;
3. updates `data/applications.json`;
4. regenerates `reports/application_tracker.csv`;
5. runs tracker tests; and
6. commits and pushes the two tracker files automatically.

No local JSON/CSV editing or Git commands are needed. The user must still select the truthful status because the radar cannot know whether an application was actually submitted without access to private email or employer accounts.

## LinkedIn feed setup

Create individual Google Alerts for searches such as:

```text
site:linkedin.com/posts "application security" hiring Germany
site:linkedin.com/posts "product security" hiring Germany
site:linkedin.com/posts "penetration tester" hiring Germany
site:linkedin.com/posts "security engineer" hiring Berlin
site:linkedin.com/posts cybersecurity hiring "remote Germany"
```

Choose English, Germany, all results and RSS delivery. Add the RSS URLs to a GitHub Actions repository secret named `LINKEDIN_POST_FEEDS_JSON`:

```json
["FIRST_RSS_URL", "SECOND_RSS_URL"]
```

The feed URLs can contain private identifiers. Never commit them to the repository.

## Validation

The v2.4 update contains 63 deterministic offline tests. Tests cover RSS parsing, redirect extraction, security/hiring filtering, score capping, offline operation, 50-job Markdown rendering and the preserved application-tracker validation.

Run before committing:

```powershell
python -m unittest discover -s tests -v
```

Expected result:

```text
Ran 63 tests
OK
```

## Privacy and safety

- Do not store LinkedIn cookies, session tokens, passwords or post content in repository secrets.
- The only optional secret is an array of feed URLs.
- Do not put recruiter contact information or private correspondence in tracker notes.
- Application records and notes are visible if the repository is public.
- The radar never applies to a job automatically.
