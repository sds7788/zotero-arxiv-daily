# Daily recommendation recovery

## Confirmed findings (2026-10-08)

- Public workflow API reports workflow 212837801 as `disabled_inactivity`.
- Latest run 21608577264 was scheduled on 2026-02-02 and ended with `failure`, about 15 minutes after creation. This is separate from the disabled scheduler. Available job metadata is incomplete and contradictory (cancelled job, no steps); it does not establish a timeout or a dependency failure.
- Cron `0 22 * * *` means 06:00 the following day in Asia/Shanghai. GitHub may delay scheduled execution.
- Python is 3.11; uv is pinned to 0.5.4. The lock pins arxiv 2.1.3, pyzotero 1.5.25, openai 1.57.0, llama-cpp-python 0.3.2 and sentence-transformers 3.3.1. There is no evidence that upgrading these resolves the historical failure, so versions are preserved and `--locked` enforces reproducibility.
- Confirmed reliability gaps: RSS, code-link lookups and SMTP have no explicit timeouts; OpenAI had nested SDK/application retries. Rendering sleeps 10 seconds per paper (up to 1,000 seconds at the default limit), in addition to source downloads and LLM work. These are risks, not proven explanations of the last failure.

## Changes

- Manual dispatch defaults to `send_email=false`, which retrieves, ranks and renders recommendations but skips SMTP entirely. SMTP credentials are omitted for this mode. Empty-day behaviour still follows SEND_EMPTY.
- Manual checkout uses the selected branch in this repository so the validation actually uses the new CLI. Scheduled checkout retains REPOSITORY/REF overrides; if configured to another repository/ref, ensure that target includes these fixes before restoring daily delivery.
- Dependency installation is separated from execution, limited to 30 minutes, and locked. Job limit is 120 minutes; overlapping deliveries are serialized.
- RSS, code lookup, SMTP and OpenAI API calls receive explicit timeouts. The existing three application retries remain for OpenAI; nested SDK retries are disabled.
- Source downloads, Zotero SDK requests, Hugging Face downloads and local LLM inference are still bounded primarily by the overall job limit. Full online validation remains required.

## Recovery and validation (requires owner approval)

Do not rerun the historical failure: it uses the old code and may send email.

1. Review and merge the repair PR. Before merging, inspect Actions settings and workflow status; do not inadvertently restore scheduled delivery without approval. Keep cron unchanged.
2. In Settings > Actions > General, confirm Actions and the required actions are allowed. Inspect only configuration and secret names, never their values. If REPOSITORY/REF variables override checkout, check that they point to the intended repaired code.
3. Enable the workflow after approval:

   ```sh
   gh workflow enable main.yml --repo sds7788/zotero-arxiv-daily
   gh api repos/sds7788/zotero-arxiv-daily/actions/workflows/main.yml --jq .state
   ```

   Expected state: `active`. Enabling also authorizes the next scheduled real email; do this only after approval for daily delivery.

4. Dispatch a no-email validation after approval:

   ```sh
   gh workflow run main.yml --repo sds7788/zotero-arxiv-daily --ref main -f send_email=false
   gh run list --repo sds7788/zotero-arxiv-daily --workflow main.yml --limit 5
   gh run watch RUN_ID --repo sds7788/zotero-arxiv-daily --exit-status
   ```

   Confirm locked dependency installation and the final dry-run message. If no new papers and SEND_EMPTY=false, the successful early exit validates retrieval but not ranking/rendering. Retry on an announcement day to validate the full path. LLM API usage, if configured, can incur costs; no SMTP call occurs.

5. Only with separate permission to send a real test email:

   ```sh
   gh workflow run main.yml --repo sds7788/zotero-arxiv-daily --ref main -f send_email=true
   ```

   Confirm successful send and actual inbox/junk delivery. SMTP acceptance alone does not prove receipt.

6. Check the next scheduled run after 06:00 Asia/Shanghai (allow delay); verify `event=schedule` and successful delivery. Public repositories without activity may be disabled again after 60 days. Periodically check workflow state and make legitimate maintenance updates; this repair does not bypass GitHub's inactivity policy.

## Offline validation

```sh
python -m unittest discover -s tests -v
python -m compileall -q main.py paper.py llm.py construct_email.py
git diff --check
```

Three mock-based CLI tests pass: dry run with papers, dry run with empty email, and normal delivery. No credentials, external APIs or email were used. Dependency installation and end-to-end online behaviour have not been validated.
