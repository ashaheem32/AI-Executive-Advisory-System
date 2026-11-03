# Understanding and explaining the prototype

This guide supports the assessment's requirement that the candidate understand, modify and troubleshoot the implementation. Reading it does not establish that the candidate has independently reviewed the system; practice each step before presenting.

## Read the system in this order

1. `app/db.py`: identify how roles, sessions, documents and jobs are stored. Explain why the browser cannot grant itself an Administrator role.
2. `app/main.py`: follow sign-in, the `user`/`admin` dependencies, the upload route and `/api/ask`. Notice CSRF, Origin checking and input bounds.
3. `app/ingest.py`: follow extraction, chunk locations, the ingestion transaction and summary job state changes. Explain what happens if parsing fails before the transaction or the server stops after a pending job is committed.
4. `app/retrieval.py`: locate the SQL access condition before scoring. Explain lexical retrieval's limitations and why a vector database would still need permission filters.
5. `app/advisors.py`: inspect intent routing, policy topics and conflict comparison. Add a synthetic policy topic and test it without changing the authentication code.
6. `app/finance.py`: hand-calculate the Q3 result, inspect metric parsing, then find where Decimal is used. Explain why operating profit is not the same as net profit or cash burn.
7. `app/provider.py`: identify the fixed provider endpoint, untrusted-source instructions, JSON schema, timeout and exact-quote check. Explain why a prompt alone is not an authorization boundary.
8. `tests/test_system.py`: run the tests, then deliberately change a calculation in a disposable copy and observe a failing test. Restore it before submission.

## Questions to practice

**Why keep this as one service?** The assessment prioritizes a small working proof of concept. One service and SQLite make installation, state inspection and demonstrations straightforward. Dedicated parser workers, a queue and managed identity become appropriate with real users and untrusted uploads.

**Where is the actual AI?** When configured, the OpenAI model selects exact relevant quotes from authorized retrieved chunks. Without credentials the app uses a clearly labelled deterministic fallback. Both modes share routing, policy checks and finance tools; the fallback should never be presented as a live model.

**Can a malicious document change the user's role?** No document text is used in an authorization expression or executed as code. Permissions come from the server session and database. The model has no role-changing tool. Exact quotes can still be irrelevant or malicious, so untrusted sources remain visibly traceable and the UI renders all content as text.

**How are hallucinations reduced?** The model cannot introduce arbitrary paraphrased facts into the response; it selects verifiable quotes. Empty or unavailable evidence returns a refusal. However lexical relevance and question completeness still require evaluation; exact provenance is not a universal truth guarantee.

**Why return 404 for confidential documents?** An inaccessible source and an unknown ID produce the same response, reducing document-existence leaks. Lists, summary records and model inputs are filtered too; protecting only the dashboard would leave direct API paths vulnerable.

**How do calculations remain trustworthy?** Inputs come from labelled financial sources, not user-provided overrides or model-generated numbers. A small operation allowlist uses Decimal. Conflicting source inputs stop the operation. Tests cover known answers, rounding, zero denominators, invalid numeric formats and reported arithmetic errors.

**What does the automation integrate with?** SQLite is the working database integration permitted by the brief. Uploads trigger summary records with job status, attempts and safe errors. An email API is a future addition, not an implemented feature.

## Useful modifications to practice

- Change the annual leave value in a new synthetic HR upload and observe the conflict.
- Add a new supported financial operation with a pure calculation function and an independently calculated expected result.
- Change the upload limit and update both the UI message and failure test.
- Add a labelled HR topic and demonstrate both agreement and conflict across two documents.
- Set an unsupported model name with a valid key in a synthetic environment and explain the labelled fallback. This invokes the provider and may have account-specific costs or limits; it was not done in the recorded demo.

## Troubleshooting exercise

For an unsupported answer, check category, permissions, query wording and retrieval overlap before changing the prompt. For a failed finance result, inspect Period, Currency, Scope and exact numeric labels. For a failed upload, check size, extension, readable text and encryption. For a failed background job, inspect its stored status and use the admin retry action. For a database outage, verify path/permissions/storage and restore availability before retrying; the browser receives a safe 503 message.
