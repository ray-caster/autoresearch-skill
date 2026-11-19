# Lateral step (the `lateral` config block)

Read this when setting up a project's lateral deck, or when the loop keeps producing variants of the same kind
of idea.

## What it does
`scripts/lateral.py` (copied to `<project>/autoresearch/lateral.py`) adds a LATERAL STEP to the researcher's
prompt at the start of a run, whenever a branch closes, and when the idea list is used up. It chooses:
- **one technique** from `autoresearch/lateral_techniques.json`. The choice is Thompson sampling on outcomes:
  Beta(1 + kept + 2·pooled, 1 + falsified + 0.5·tried) per technique, credited through the `"technique"` tag on
  each idea, with a penalty for repeating the last technique;
- **one random stimulus** of that technique's kind:
  - `kb_card`: a knowledge-base card from a near, middle or far field (weights in `distance_weights`);
  - `book`: a title from `lateral_books.md`, or a textbook from the kb;
  - `field`: an under-used input from `reference/fields.tsv`, when the project has one;
  - `pool_alpha`: a pooled result to invert or abstract;
  - `provocation`, `assumption`, `persona`, `triz`: one entry from the deck's lists;
  - `morph_cell`: one random cell of the deck's design-space box.

  A kind whose source is missing falls back (field → kb card → provocation), so a project with no kb still works.

The researcher follows a fixed protocol:
1. Abstract the target in functional terms.
2. Write five direction titles, then revise them so they differ.
3. Map by function, not by surface.
4. Write concrete, checkable changes.
5. Remove ideas already tried, last.

It adds at least `n_ideas` ideas tagged with `"technique"` and `"stimulus"`. On every `forced_seed_every`-th
branch close, the best lateral idea must be ranked first, so it seeds the next branch.

Outputs:
- `state.json` → `lateral_log` (technique, stimulus, idea ids per brief);
- `runs/lateral_stats.md` (per-technique outcome table);
- `runs/literature_log.md`, written by the driver after every researcher call (notes plus new sources, never
  overwritten). Later calls read it instead of repeating searches.

Config (template default):
`"lateral": {"enabled": true, "deck": "autoresearch/lateral_techniques.json", "books": "autoresearch/lateral_books.md", "n_ideas": 3, "forced_seed_every": 2}`.
Optional keys: `kb` (path to kb.sqlite), `fields`, `distance_weights`. Leave the block out to switch it off; the
researcher prompt is then unchanged.

## Setting up a project's deck
Copy `templates/lateral_techniques.json` and `templates/lateral_books.md` into `autoresearch/`. Then customise:
- **protocol step 1**: what a "good change" is in this domain. For BRAIN alphas: "a daily-observable trace of
  participants being systematically wrong, persisting because correcting it is costly";
- **provocations, assumptions, personas**: assumptions should be the program.md recipe's own soft rules;
- **morph**: the project's real design axes (data × transform × comparison × horizon × condition for alphas;
  topology × component × control law for circuits).

`Projects/Quant/brain-alpha/autoresearch/lateral_techniques.json` is a worked example. Add books or techniques
whenever the user names one, and keep technique ids stable.

## Why it is built this way (evidence, Nov 2026)
- **Random words alone are weak.** A pre-registered study (592 people) found no effect from arbitrary random
  stimuli: they must be "optimally random", related enough to the task to use
  ([Warwick 2021](https://wrap.warwick.ac.uk/159029/1/WRAP-influence-exposure-randomness-lateral-thinking-divergent-convergent-creative-2021.pdf)).
  Adding a random concept does raise LLM output diversity, but more random words add nothing
  ([arXiv 2601.18053](https://arxiv.org/pdf/2601.18053)). So every stimulus comes with a technique that forces
  a functional mapping.
- **Structured analogy beats "think cross-domain".** Extracting objects and relations, mapping by function and
  searching the target side gave 50-69% novel solutions, against 22-38% for plain cross-domain prompting. The
  cost: fewer were feasible (67% vs 86% judged reasonable)
  ([arXiv 2605.11258](https://arxiv.org/html/2605.11258v1)). Hence the field-name check and "drop what the
  evaluator cannot measure" step.
- **Far sources are mixed.** They raise novelty but cost effort and sometimes quality
  ([Chan, Dow & Schunn 2015](https://www.lrdc.pitt.edu/Schunn/papers/Chan-Dow-Schun-desstudies-nearfar-inpress.pdf)).
  Hence the near/mid/far mix, and outcome tracking instead of always going far.
- **Plan distinct directions first.** Five planned strata, then one idea per stratum, reached the diversity of
  independent sampling 2.4 times faster ([arXiv 2605.30150](https://arxiv.org/pdf/2605.30150)).
- **Personas help across calls but fixate within one.** Chain-of-thought (titles first, then revise them to
  differ) undoes the fixation ([Deng, Brucks & Toubia, arXiv 2602.20408](https://arxiv.org/html/2602.20408v2)).
  Hence "five titles, revise to differ" in every brief, and personas only as a lens.
- **Listing previous ideas and asking for new ones cuts duplicates**
  ([Si et al., ICLR 2025](https://arxiv.org/abs/2409.04109)). The step therefore de-duplicates against the
  history, but only after generating, to avoid anchoring.
- de Bono's techniques (random entry, Po provocation, concept fan, challenge) have little rigorous testing on
  their own ([Wikipedia: Lateral thinking](https://en.wikipedia.org/wiki/Lateral_thinking)). That is why the
  bandit, not belief, decides how often each one is used.
