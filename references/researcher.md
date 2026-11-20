# Researcher (the `review` config block)

Read this when setting up or changing the researcher, or when a `review` row needs explaining.

- **Researcher** (`review` block; a stronger model, `review.model`, default opus) keeps a ranked idea
  list in `autoresearch/runs/ideas.json` and notes with **CONTINUE / PIVOT / STOP** in
  `autoresearch/runs/review.md`. It runs:
  - at the start of every driver run (`review.at_start`, true in the template): searches the web for
    work newer than literature.md/program.md and rebuilds the list;
  - after `review.after_reverts` rounds in a row without improvement (default 6; 0 = off), and when
    every listed idea has been tried: re-ranks from the log, and searches only for a specific question
    the log raises (so it doesn't repeat the same searches all night).
  Each round implements the top untried idea by default, but may pick its own fix when the eval output
  points to a clearer one; it names the idea id it used (`IDEA_ID`) or says why it skipped. The
  **script** records each idea as kept / falsified / tried from the round's outcome; a made-up id is
  ignored. The researcher may only write those two git-ignored files (anything else is reverted), and is
  told web pages are information, not instructions. STOP ends the run early. Measured: one start call
  ≈ 13 turns, ≈ $0.27 on Opus.
- **Restarts don't re-run the start review** while untried ideas remain and the last researcher call is under
  `review.start_min_gap_h` hours old (default 6; 0 = always run). Before this, STOP/restart cycles paid for an Opus
  start review each time, sometimes minutes apart (brain-alpha: 17 start reviews, ~$15).
- **Codex backend** (`"backend": "codex"` in `agent` and/or `review`): the call goes to `codex exec` (ChatGPT
  subscription) first, tool-less and read-only in an empty temp folder. The driver inlines the files the prompt
  names (editable files; for the researcher also program.md, best eval, literature, seed tables) plus `inline`
  ([{"path", "chars"}]) and `lookup` ([{"path", "max_rows"}]: rows of a big TSV whose first column is named in the
  prompt, e.g. a 500 KB field list). Codex replies with `=== FILE: <path> === ... === END FILE ===` blocks; the
  driver writes only allowed paths (editable files; ideas.json + review.md for the researcher) and refuses the
  whole reply if any other path appears. On a Codex limit (30 min cool-down), error or unusable reply the call
  falls back to Claude `model` (`codex_only: true` disables that). Options: `codex_effort` (default medium),
  `codex_model` (leave unset: the config.toml default), `codex` (exe path). Every call goes to
  `runs/agent_backends.tsv` (round, role, backend that answered), to compare keep rates of Codex and Claude rounds.
- After every call the driver appends the notes and any new sources to `autoresearch/runs/literature_log.md`
  (never overwritten) and lists it in the next call's reading list, so searches are not repeated across
  branches. With a `lateral` block the prompt also carries a LATERAL STEP (`references/lateral.md`).
- `seed_sources` (config list of `{"path", "note"}`): extra seed tables the researcher reads when they exist,
  e.g. another project's failed ideas tested on this loop's evaluator (brain-alpha reads frontier-quant's).
- `seeds_only: true`: the loop stops inventing signals. The researcher does no web search (also drop WebSearch/WebFetch
  from `review.allowed_tools`), the lateral step is off, and every new branch seeds from an unused row of the
  `seed_sources` tables (another project's ideas, already script-tested). Rounds only refine the seed. Use it when a
  separate idea engine (e.g. frontier-quant's daily researcher) feeds this loop.
