# Optional model APIs

The host agent remains the default planner. Use an API only when the user selects
it. The provider drafts from the skill's daily or weekly contract; shared helpers
validate the result. No browser or Flask dependency is needed for these helpers.

## Connect

In the companion's **Setting → API connections** section, choose a provider, enter an exact model ID,
select credential storage, and save. Keys belong in this local form or a hidden
terminal prompt, never in the agent conversation, command arguments, or planner files.

| Provider | Fixed API host | Environment variable |
| --- | --- | --- |
| [OpenAI](https://developers.openai.com/api/reference/overview) | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| [Grok / xAI](https://docs.x.ai/developers/model-capabilities/legacy/chat-completions) | `https://api.x.ai/v1` | `XAI_API_KEY` |
| [OpenRouter](https://openrouter.ai/docs/api/reference/authentication) | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| [Sakana AI](https://console.sakana.ai/get-started) | `https://api.sakana.ai/v1` | `SAKANA_API_KEY` |

Model IDs must support Chat Completions and JSON-object output. **Test connection**
checks credentials and the model catalog without sending planner context; it does
not prove generation compatibility. OpenRouter also checks its authenticated key
endpoint because its model catalog is public.

OpenRouter requires one upstream provider slug. Requests disable fallback, require
parameter support, and exclude routes permitting data collection. See its
[routing controls](https://openrouter.ai/docs/guides/routing/provider-selection).
Sakana's Fugu can send context to multiple model providers: restrict the model pool
when creating/editing the key in Sakana's console. No custom API hosts are accepted.

## Choose storage

- **System keychain:** persists through restarts using a known macOS Keychain,
  Windows Credential Locker, or Linux Secret Service backend. Requires `keyring`
  and OS support. Failure never falls back to plaintext.
- **Temporary:** keeps the key in server memory until disconnect or process exit.
  Browser reloads do not erase it. Available through the UI only.
- **Environment:** reads the provider variable from the process environment.
  Supply it through your own secret manager or secure shell setup; the app does
  not write or automatically load an `.env` file.

Only provider/model/storage/upstream metadata goes to
`DATA_DIR/config/connections.json`. GET responses, usage logs, and browser storage
never contain the saved key. Disconnect removes app-managed credentials and
metadata; it cannot revoke a provider key or unset a process environment variable.
Local keychains do not isolate secrets from every process running as the same
user; see [keyring's security considerations](https://keyring.readthedocs.io/en/latest/#security-considerations).

## Plan

Select the configured API in **Agent Plan / Run Today's Flow** or weekly setup.
Generation sends saved goals, selected project/week context, relevant local
outcome summaries, and your answers to the selected provider. Daily generation
also includes today's tasks, backlog, and the recent local work report. Starting
the UI, listing connections, and saving settings make no provider requests.

Daily planning returns questions or a validated draft. Review the full plan and
choose **Apply this plan** to save it. Changes to source context invalidate the
draft; drafts also expire after 15 minutes or a server restart. Applying preserves
completed/canceled work and feedback and uses normal rollover and save helpers.
Weekly setup retains its existing explicit generate-and-save action.

Requests provide no tools, reject redirects and incomplete/non-JSON output, and
never execute model text. Each request has a 60-second timeout, a bounded input,
and a 4,096 final-output-token limit. These are not spending limits: input tokens
and provider orchestration can cost extra, including
[Fugu orchestration](https://console.sakana.ai/models). Use provider billing controls.
There are no automatic retries or automatic switches to another connection.
`DATA_DIR/data/api_usage.jsonl` records available usage counts and call metadata,
without prompts, responses, or secrets. It is not an authoritative billing ledger.

## Headless commands

With the provider variable already supplied securely:

```sh
python3 "$SKILL_DIR/scripts/pm.py" --data-dir "$DATA_DIR" connect \
  --provider openai --model YOUR_MODEL_ID --storage environment
python3 "$SKILL_DIR/scripts/pm.py" --data-dir "$DATA_DIR" test-connection --provider openai
python3 "$SKILL_DIR/scripts/pm.py" --data-dir "$DATA_DIR" api-draft \
  --provider openai --context-file /path/to/private-session-notes.txt
```

Use `--storage keychain` in an interactive terminal for hidden key input. OpenRouter
also needs `--upstream PROVIDER_SLUG`. `connections` lists safe metadata;
`disconnect --provider PROVIDER` removes a connection.

`api-draft` returns JSON with questions or validated `plan_markdown`; it never
applies the plan. Review it in conversation, answer consequential questions, and
save the accepted Markdown using [daily planning's](daily-planning.md) ordinary
rollover/save-plan commands. Do not call another paid API just to validate formatting.

The companion binds to loopback and protects API access with local browser
sessions, same-origin checks, CSRF tokens, and bundled scripts. It is a local app,
not a multi-user hosted credential service. Keep real data roots out of git.
