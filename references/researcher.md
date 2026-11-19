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
- After every call the driver appends the notes and any new sources to `autoresearch/runs/literature_log.md`
  (never overwritten) and lists it in the next call's reading list, so searches are not repeated across
  branches. With a `lateral` block the prompt also carries a LATERAL STEP (`references/lateral.md`).
- `seed_sources` (config list of `{"path", "note"}`): extra seed tables the researcher reads when they exist,
  e.g. another project's failed ideas tested on this loop's evaluator (brain-alpha reads frontier-quant's).
- `seeds_only: true`: the loop stops inventing signals. The researcher does no web search (also drop WebSearch/WebFetch
  from `review.allowed_tools`), the lateral step is off, and every new branch seeds from an unused row of the
  `seed_sources` tables (another project's ideas, already script-tested). Rounds only refine the seed. Use it when a
  separate idea engine (e.g. frontier-quant's daily researcher) feeds this loop.
