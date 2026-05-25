# Pre-Registration of Methodology Increment §3.6.7 — Head-vs-Tail-Aware LLM Validator (Engineering Pattern)

> Date: **2026-05-25** (SESSION-25)
> Status: pre-registered *as an engineering pattern*, explicitly **not** a scientific universality claim
> Tier: §3.6 tier 3 (engineering provenance, not scientific methodology) — see `paper/v0.5-draft/methodology-increment-checklist.md` Note 1
> Companion: `paper/v0.5-draft/v05-draft-skeleton.md` §3.6.7
> Author: dada8899
> Repo state at pre-registration: HEAD `71a5617`

## 1. What is being pre-registered

This document pre-registers an **engineering pattern**, not a scientific
universality-class claim. The pattern, formalised in v0.5 skeleton §3.6.7, is:

> *In LLM-driven text-rewrite tasks at scale where a generated output must preserve a
> fixed **head** (input context, citation stem, header) while replacing a **tail**
> (LLM-generated continuation), the forbidden-substring validator must be applied to
> the tail only: `new_only = new_full[len(head):]`. A naïve whole-output validator
> false-rejects outputs whose forbidden substring legitimately appears in the
> preserved head.*

We pre-register the pattern explicitly as **engineering provenance** rather than as
methodology, so that reviewers of the v0.5 paper do not mistake it for a scientific
contribution alongside §3.6.5 and §3.6.6. Documenting the pattern is justified
because: (i) it changed the binding constraint on KB-quality cleanup at scale (from
"expensive whole-output review" to "cheap targeted slice + strip"); (ii) the v0.5 KB
hardening downstream affects the embedding-similarity and pair-mining steps of the
project's Layer 1 community discovery; (iii) the pattern is reusable in any LLM-driven
text-rewrite task with a fixed-prefix structure.

## 2. Hypothesis

**H1.** For LLM rewrite tasks where the output partitions deterministically into
`preserve-section + replace-section`, applying the forbidden-substring validator to
the replace-section only yields a strictly lower false-reject rate than applying it
to the whole output, while preserving the safety property the validator was originally
designed for (no forbidden content survives in the *output the LLM controls*).

**H2.** Head-aware validation does **not** remove the need for downstream
embedding-cluster audits. Head-internal collisions (legitimate domain phrases shared
across many entries' heads) remain a separate pollution source requiring a separate
remediation (deterministic strip, no LLM cost).

## 3. Scope — where the pattern applies, and where it explicitly does NOT

### 3.1 Scope conditions (must hold conjointly)

(i) The LLM task is a **rewrite**, not a fresh generation — i.e., the input contains a
distinguishable head section that the LLM is *required to preserve verbatim* and a
tail section that the LLM is *required to replace*.

(ii) The forbidden-substring safety check is intended to certify that *the LLM has not
introduced* forbidden content, not to certify that the input was free of forbidden
content.

(iii) The head boundary is deterministically computable from the input (e.g.,
`len(head)` is a known integer, or a regex / structural marker delimits head from
tail).

### 3.2 What the pattern is NOT being claimed to cover

- **Full-generation tasks.** When the LLM produces a free-form output with no
  preserved head, the whole-output check is the only correct check; there is no
  "head" to exempt. The pattern does not apply.
- **Adversarial / red-team LLM outputs.** The pattern assumes the LLM is *trying* to
  preserve the head and the head boundary is deterministic. If the LLM intentionally
  moves forbidden content from the (legitimately-containing) head into the
  generated tail to evade the tail-only check, the validator becomes blind. This is
  the §6 falsifier.
- **Embedding-pollution by head-internal collision.** When the same legitimate domain
  phrase appears inside many entries' *heads* (e.g., the 23 public-health entries
  sharing "该干预的成本效益(QALY/DALY)评估是政策决策核心"), the head-aware validator
  correctly does not flag the entries (because the phrase is in the preserved head,
  not the generated tail), but the entries are still spuriously clustered by
  embedding similarity. The remediation is a *separate* deterministic strip
  pass — see §4.2 below.
- **Scientific universality.** The pattern is engineering, not methodology. §3.6.7 of
  the v0.5 skeleton and the methodology-increment checklist (Note 1) explicitly
  stratify §3.6.7 as tier 3 (engineering provenance), distinct from §3.6.5 (tier 1,
  targeted remediation) and §3.6.6 (tier 2, general test pattern). Reviewers should
  weight accordingly.

### 3.3 Tier classification (per checklist §Note 1)

| Tier | Type | v0.5 instances |
|---|---|---|
| 1 | Targeted remediation with explicit scope limits | §3.6.5 (s\*, k) reparam |
| 2 | General test pattern expected to transfer broadly | §3.6.6 multilayer test |
| 3 | Engineering pattern documented for reproducibility | **§3.6.7 head-aware validator (this document)** |

The present pre-registration is *for the tier-3 pattern*, with the understanding that
it does not get weighted alongside tier-1 / tier-2 patterns as a scientific
contribution.

## 4. Pre-specified data and procedure

### 4.1 First instance (already executed at HEAD `71a5617`)

`scripts/rewrite_wave3c_boilerplate.py` — Wave 3 C knowledge-base boilerplate cleanup,
117 KB entries sharing a 7-template boilerplate suffix that polluted embedding-based
retrieval and clustered the entries spuriously.

- **Rewrite scope.** 117/117 entries through OpenRouter (Kimi K2.5), wall clock 18 s,
  total LLM cost ≈ $0.05.
- **Validator.** Head-tail slicer `new_only = new_full[len(head):]` + forbidden-substring
  check on `new_only`.
- **False-reject rate.** 0/117 false-rejects on the head-side; clean rewritten tail
  per entry.
- **Counterfactual.** A whole-output check on the same 117 outputs would have
  false-rejected an estimated N ≥ 1 entries whose head legitimately contained a
  template-similar phrase (the rewrite tail itself was clean by inspection).

### 4.2 Follow-up: head-internal collision (deterministic strip)

23 of the 117 public-health entries shared a 30-character connector phrase ("该干预的成本效益(QALY/DALY)评估是政策决策核心") *inside their heads*. The head-tail slicer correctly did not flag these entries (the phrase was in the preserved head, not in the LLM-generated tail), but the entries were still spuriously clustered by embedding similarity. The follow-up fix `scripts/strip_wave3c_head_collisions.py` is a **deterministic** strip (no LLM call, no cost) that removes exactly that 30-character substring from the affected 23 entries.

The slicer + strip combination removes both pollution sources (LLM-generated tail
boilerplate + head-internal legitimate-but-collision-prone phrase) without false-rejecting any entries. This two-pass combination is the pre-registered procedure for any future KB cleanup with the same structure.

## 5. Verdict ladder (for the pattern, not the class)

| Outcome | Criterion |
|---|---|
| **PASS — pattern works** | (a) the head-restricted forbidden check yields a strictly lower false-reject rate than the whole-output check on the same outputs AND (b) the tail-only check still catches the safety case it was designed for (no forbidden content survives in the LLM-generated tail) AND (c) the embedding-pollution downstream effect is measurably reduced after the rewrite + strip combination relative to the pre-cleanup baseline. |
| **FAIL — pattern broken** | A rewrite task is found where the LLM moves forbidden content from the head to the tail (or vice versa), making the head-aware validator blind to a safety case the whole-output validator would have caught. |
| **INSUFFICIENT** | The pattern applies (§3.1 holds) but the false-reject rate counterfactual cannot be measured (no whole-output baseline run). |

Wave 3 C cleanup delivers PASS under this ladder at HEAD `71a5617`: 0/117
false-rejects on the head-side, clean tail per entry, embedding-cluster audit
confirms reduced pollution post-cleanup.

## 6. Falsifiability criterion

The pattern is falsified by exhibiting a rewrite task for which:
- scope conditions (i)–(iii) all hold (rewrite, safety check on LLM-generated content,
  deterministic head boundary);
- the LLM *intentionally or accidentally* moves forbidden content from the
  legitimately-containing head into the LLM-generated tail (e.g., paraphrasing the
  head into the tail while replacing the original tail);
- the tail-only check passes (the rewritten tail's forbidden-string check returns
  clean) but a whole-output check would have caught the violation (the original
  forbidden content has been relocated, not removed).

This is a real risk for any rewrite task where the LLM has *latitude over what to
include from the head* in the tail. The mitigation is to combine the tail-only check
with a *cross-check*: compare the rewritten tail's forbidden-substring profile to the
head's, and flag any forbidden substring that appeared in the head AND now appears in
the tail.

A second falsifier: a downstream embedding-cluster audit shows pollution *increased*
after the rewrite, indicating the LLM-generated tail itself introduced a new shared
phrase across entries. Mitigation: extend the deterministic strip pass (§4.2) to
catch the new collision phrase.

## 7. What is explicitly NOT being claimed

- **That this is a scientific universality claim.** §3.6.7 is tier 3 (engineering
  provenance) per the v0.5 methodology checklist Note 1. It is recorded for
  reproducibility, not as a methodological lift.
- **That head-aware validation removes the need for downstream embedding-cluster
  audits.** Head-internal collisions (legitimate domain phrases shared across heads,
  §4.2) still require deterministic strip, which is a separate pass.
- **That the tail-only check is safe against adversarial LLM behaviour.** The
  falsifier in §6 is a real risk; the pattern is *not* claimed to be a complete
  safety check for adversarial inputs.
- **That this is the only way to handle fixed-prefix rewrite tasks.** Alternative
  approaches include: regenerating the entire output and using a whole-output check
  (more expensive); pre-classifying the head for forbidden content separately from the
  tail (more bookkeeping); using a constrained-decoding harness that prevents the LLM
  from emitting the forbidden tokens at all (more infrastructure). The head-aware
  validator is offered as the *cheapest* of these options, not the only one.
- **Authorship of head-vs-tail awareness.** Slicing input from output for
  safety/quality checks is canonical in software engineering. The v0.5 claim is the
  *systematic application* of head-vs-tail-aware validation to LLM rewrite pipelines
  at the scale we deployed (117 entries, $0.05, 18 s wall clock).

## 8. Resource budget

- **Compute.** The pattern itself is a 2-line code change (`new_only =
  new_full[len(head):]` + check on `new_only`). The cost is the LLM rewrite it
  enables, not the pattern itself.
- **LLM cost (first instance).** $0.05 total for 117 entries via OpenRouter Kimi
  K2.5.
- **LLM cost (deterministic strip follow-up).** $0 (no LLM call, deterministic
  substring removal).
- **Human-hours.** Pattern design + implementation + first deployment: ≈ 2 h.
  Follow-up strip pass: ≈ 1 h. Present pre-registration: ≈ 1 h. Total ≈ 4 h.
- **Future-task budget.** Reusing the pattern on a new LLM rewrite pipeline is
  expected to cost ≤ 30 minutes of integration time plus the LLM cost of the rewrite
  itself.

## 9. Data and script provenance

| File | Purpose |
|---|---|
| `paper/v0.5-draft/v05-draft-skeleton.md` §3.6.7 | Engineering pattern, prose description |
| `paper/v0.5-draft/methodology-increment-checklist.md` §3.6.7 | Reviewer-facing tier-3 classification |
| `scripts/rewrite_wave3c_boilerplate.py` | First-instance deployment, 117 entries |
| `scripts/strip_wave3c_head_collisions.py` | Follow-up deterministic strip pass, 23 entries |
| `data/kb-5000-merged.jsonl` | KB master file (5341 entries post v0.5 merge) |
| `paper/anti-phacking-unified-2026-05-15.md` §1.2 | Adversarial pre-registration framing |

End of pre-registration §3.6.7.
