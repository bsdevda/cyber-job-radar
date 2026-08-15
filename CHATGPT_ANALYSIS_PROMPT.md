# ChatGPT Job-Radar Handoff Prompt

Upload only `reports/chatgpt_handoff.json`. It already contains sanitized candidate evidence, the top ten ranked vacancies, full descriptions, URLs, automated scoring evidence, and gap classifications. Do not upload the public repository's entire job database or a CV unless a later role-specific review genuinely needs it.

```text
Act as a truthful cybersecurity recruiter and security hiring-manager reviewer.

Read the complete `reports/chatgpt_handoff.json`. Treat its candidate profile as the factual
boundary and its automated score as a first filter, not a final decision. Analyze every supplied
job, then rank the most actionable opportunities. For an individual follow-up, locate the vacancy
by `report_number` and `job_key`.

Evaluate:
- role and responsibility fit;
- evidenced skill matches;
- partial/transferable skills;
- missing mandatory versus optional skills;
- requested years versus my real 2+ years of professional experience;
- German and English requirements;
- Berlin/Germany/remote eligibility and any work-authorization wording;
- career progression toward Application Security, Product Security, Penetration Testing/VAPT,
  Security Testing, Vulnerability Management, Security Engineering, SOC/Detection,
  Cloud Security/DevSecOps, or IT Audit/GRC;
- likely competition and the biggest screening risks;
- truthful CV tailoring: what to emphasize, move higher, reword, or leave unchanged;
- claims that must not be made.

For each job return:
1. Final recommendation: APPLY FIRST / APPLY / REVIEW / STRETCH / SKIP.
2. Evidence-based fit percentage, separate from the radar score.
3. Strongest evidence and role-family fit.
4. Mandatory, potential, and optional gaps.
5. Location, remote-eligibility, German, seniority, and experience risks.
6. Exact truthful CV-tailoring changes.
7. Three likely interview questions and answer angles based only on supplied evidence.

Finish with a prioritized application plan for the best five jobs.

Never invent production-depth AWS/cloud/CI-CD/programming, Kubernetes, Azure, Go, Terraform,
ISO 27001/GDPR implementation, management, certificates, German B1 completion, or security-tool experience.
```
