# Verification results

Verified on **3 November 2026**, using Python 3.12.14 on macOS with the runtime versions pinned in `requirements.lock`.

## Automated checks

```text
python -m pytest -q
55 passed, 1 warning in 3.67s
```

The warning comes from the installed Starlette TestClient's deprecation of its HTTPX integration in favor of HTTPX2. It does not fail the suite. HTTPX remains the application's provider client. No warning was suppressed.

| Area | Observed behavior |
|---|---|
| Financial tools | Independently specified expected results for all six operations, decimal rounding, a small fractional amount, negative profit, nonfinite inputs and zero denominators |
| Source arithmetic | The intentionally reported 45% Q3 margin is flagged; code returns 40% with original input citations |
| Source conflicts | Different same-period financial values stop calculation; missing, malformed and inconsistent-scope inputs fail safely |
| Routing | Finance, HR, knowledge and mixed-intent routes exercised |
| HR / general evidence | Annual leave answered; remote work conflict preserved; parental leave and unrelated questions refused; company services retrieved |
| Access control | Standard User cannot list restricted text/summaries, fetch a known restricted ID, get it through the assistant, upload, retry jobs or inspect admin audit metadata |
| Provider boundary | Mocked provider captures only authorized candidate chunks; secret marker absent from its input |
| Authentication | CSRF, cross-origin requests, forged role header, logout invalidation, generic login errors and repeated failed-login limits exercised |
| Uploads | Text, real PDF and DOCX/table extraction; corrupt/blank/unsupported files, traversal filenames, input-size and archive-expansion limits |
| Automation | Summary saved to SQLite, duplicate upload deduplicated, failure recorded, retry succeeds, completed jobs idempotent and interrupted jobs recover to pending |
| Provider reliability | Valid structured response; invalid quote/ID; incomplete response; timeout and HTTP 401/429/503 all exercise validation or fallback paths |
| Service failures | Database exception returns safe 503; body/question limits, health check, CSP and static-path protections checked |

## Browser verification

Using the running application and its actual UI:

- Administrator sign-in, Q3 margin correction, 20% revenue growth and opening the original cited document.
- Annual leave answer, remote work conflict and parental leave refusal.
- A newly uploaded synthetic Q4 PDF triggers a completed database summary and returns a 46% margin with page references.
- A newly uploaded synthetic Word document returns its AED 2,000 training budget with a Word passage reference.
- Administrator retrieves the synthetic executive salary; Standard User receives insufficient evidence for the same question.
- The exact confidential source URL observed in the Administrator's source request returns `{"detail":"Document not found."}` under the Standard User session.
- Standard User's library omits the confidential document and its summary; upload and audit actions are absent.
- General company services question returns the matching source excerpt.
- At a 390-pixel mobile breakpoint, the page has no horizontal document overflow and sign-out remains available. Desktop layout was also inspected.
- Browser error log was empty during the checked workflow. Sample PDF and Word page renders were visually inspected.

`demo.mp4` is a captioned visual walkthrough of actual local browser screenshots, not a continuous screen capture or a narrated candidate presentation. It uses local evidence mode. The underlying screenshots are not fabricated model responses.

## Verification limits

No real OpenAI credential was supplied or used. The external API's request and response protocol was tested with HTTP mocks; live account/model access, latency and costs remain unverified. No email or webhook delivery is implemented. The Docker recipe and production infrastructure were not executed. This is not a penetration test, a large-corpus retrieval evaluation or a security certification. Database storage is not encrypted by the app, parsers are not process-isolated, and English lexical recall and labelled policy conflict detection have the limits described in the README.
