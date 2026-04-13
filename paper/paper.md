# Beyond Semantic Similarity: Contrastive Learning for Cross-Domain Structural Isomorphism Detection

## Abstract

Scientific breakthroughs frequently arise from recognizing that two phenomena in unrelated domains share the same underlying mathematical structure --- a property we term *structural isomorphism*. Yet existing sentence embedding models conflate structural similarity with surface semantic similarity, failing to detect connections such as that between heat conduction and option pricing (both governed by the diffusion equation). We introduce the **Structural Isomorphism Benchmark Dataset (SIBD)**, comprising 1,214 cross-domain natural language descriptions spanning 84 mathematical structure types and 20 categories, and fine-tune a Chinese BERT-based sentence encoder (110M parameters) using contrastive learning with 8,223 positive pairs. After training, the model achieves a Silhouette Score of 0.85 (up from -0.01), Retrieval@5 of 100% (up from 20.3%), and expands the intra-class versus inter-class similarity gap from 0.074 to 0.758. Applied at scale to a knowledge base of 500 scientific phenomena, our V2 pipeline identifies 3,017 high-similarity cross-domain pairs, from which multi-round LLM screening and equation-level verification yield 6 discoveries with confirmed mathematical correspondence. We further develop a **V3 pipeline** that replaces pure embedding cosine similarity with a **StructTuple** structured representation (state variables, dynamics family, feedback topology, boundary behavior, timescale, canonical equation) followed by LLM pairwise reranking. Applied to an expanded knowledge base of 4,443 phenomena, V3 extracts 2,625 matchable items and produces 203 paper-worthy candidates (20.3%, a 3.4$\times$ improvement over V2's 6%) and 54 actionable findings after deep analysis, with every top candidate accompanied by an explicit shared equation and variable-level mapping. Across V1, V2, and V3 the top discoveries exhibit **zero overlap** (63 independent candidates), indicating that the three pipelines are complementary views rather than redundant. Three counter-experiments establish that the framework covers approximately 60% of known scientific innovations, identify six blocking mechanisms that prevent structural similarity from translating into innovation, and confirm discriminability against random baselines (average score 1.27 vs. 4.5 for innovation cases). We release the dataset, model, and full pipeline to support future research on AI-assisted scientific discovery.

---

## 1. Introduction

Many of the most celebrated scientific breakthroughs share a common pattern: a researcher recognizes that a well-understood structure in one domain applies, in transformed form, to an apparently unrelated domain. Shannon borrowed the concept of entropy from thermodynamics to found information theory [Shannon, 1948]. Black and Scholes mapped the heat equation onto financial derivatives pricing [Black and Scholes, 1973]. Simulated annealing transplanted the metallurgical process of slow cooling into combinatorial optimization [Kirkpatrick et al., 1983]. In each case, the surface-level vocabularies of the source and target domains share almost nothing in common, yet the underlying mathematical structure is isomorphic.

This observation suggests a concrete, falsifiable hypothesis: **a significant fraction of cross-domain innovation can be modeled as the detection and transfer of deep structural isomorphism across high semantic distance**. If this is correct, then a tool that can systematically identify such isomorphisms --- where domains appear semantically distant yet structurally aligned --- could accelerate scientific discovery by surfacing connections that would otherwise remain in researchers' collective blind spots.

Current AI approaches to scientific discovery have made impressive strides. Large language models can generate hypotheses [Lu et al., 2024], automated systems can design and execute experiments [Lu et al., 2024; Gottweis et al., 2025], and reasoning models can solve complex mathematical problems [Trinh et al., 2024]. However, these systems predominantly operate *within* domains. The cross-domain structural transfer that characterizes many foundational discoveries --- recognizing that protein folding and spin glasses share the same energy landscape, or that PageRank and academic citation networks obey the same eigenvector dynamics --- remains largely beyond their reach.

The core technical challenge is that modern sentence embedding models are optimized for *semantic* similarity. When asked to compare "radioactive atoms decay at a rate proportional to the remaining quantity" and "drug concentration in the bloodstream decreases at a rate proportional to the current level," these models assign moderate similarity because the domains (nuclear physics and pharmacology) share few surface keywords. Yet both descriptions instantiate the same mathematical structure: exponential decay, $Y = Y_0 e^{-kt}$. A model that could see through surface semantics to detect such structural correspondence would open a new class of applications.

**Contributions.** This paper makes three contributions:

1. **The Structural Isomorphism Benchmark Dataset (SIBD)**: a curated dataset of 1,214 cross-domain natural language descriptions across 84 mathematical structure types organized into 20 categories, designed to train and evaluate models on structural (rather than semantic) similarity.

2. **A contrastive learning method** that fine-tunes a pretrained sentence encoder to distinguish structural similarity from semantic similarity, achieving dramatic improvements on clustering and retrieval metrics.

3. **A large-scale cross-domain discovery pipeline** that applies the trained model to 500 scientific phenomena, producing 3,017 candidate cross-domain pairs and ultimately 6 equation-verified discoveries, accompanied by critical analysis of failure modes and limitations.

---

## 2. Related Work

### 2.1 Analogical Reasoning and Structure Mapping

Gentner's Structure Mapping Theory (SMT) [Gentner, 1983] established the theoretical foundation for computational analogy by distinguishing structural alignment (shared relational patterns) from surface similarity (shared object attributes). Subsequent work on the Structure Mapping Engine (SME) [Falkenhainer et al., 1989] provided algorithmic implementations, and Learning Analogies by Collaborating (LABC) [Turney, 2008] explored corpus-based approaches. More recently, large language models have shown emergent analogical reasoning capabilities [Webb et al., 2023], though these remain limited to within-context analogies rather than systematic cross-domain search. Our work operationalizes Gentner's distinction at scale by training an embedding model that explicitly learns structural rather than semantic similarity.

### 2.2 AI for Scientific Discovery

The past two years have seen rapid progress in AI systems for science. The AI Scientist [Lu et al., 2024] demonstrated end-to-end automated research including idea generation, experimentation, and paper writing. Google's AI Co-Scientist [Gottweis et al., 2025] showed multi-agent systems could generate and validate scientific hypotheses. DeepMind's AlphaFold [Jumper et al., 2021] and AlphaGeometry [Trinh et al., 2024] achieved breakthroughs in protein structure prediction and mathematical reasoning. FunSearch [Romera-Paredes et al., 2024] used large language models to discover new mathematical constructions. However, these systems primarily operate within single domains. Our approach is orthogonal: rather than solving problems within a domain, we aim to discover *connections between* domains that may inspire new problem formulations.

### 2.3 Sentence Embeddings and Contrastive Learning

Sentence-BERT [Reimers and Gurevych, 2019] demonstrated that fine-tuning BERT with siamese networks produces semantically meaningful sentence embeddings. SimCSE [Gao et al., 2021] showed that simple contrastive objectives could dramatically improve embedding quality. More recent work on instruction-tuned embeddings [Su et al., 2023] and task-aware retrieval [Xiao et al., 2024] has pushed the frontier further. Our work applies contrastive learning to a fundamentally different objective --- learning *structural* rather than *semantic* similarity --- using mathematical isomorphism as ground-truth supervision.

### 2.4 Cross-Domain Knowledge Transfer

Systematic cross-domain innovation has been pursued through several frameworks. TRIZ [Altshuller, 1996] codifies inventive principles extracted from patent analysis. Biomimicry databases [Helms et al., 2009] catalog nature-inspired design solutions. AskNature [Deldin and Schuknecht, 2014] provides a structured repository linking biological strategies to engineering challenges. Analogy mining from patent databases [Fu et al., 2013; Hope et al., 2017] uses NLP to find functional analogies across technological domains. Our approach differs in three ways: (1) we use mathematical structure types as an intermediate representation, providing a more rigorous basis for comparison than functional descriptions; (2) we train a dedicated embedding model rather than relying on general-purpose embeddings; and (3) we validate our framework through counter-experiments, not just positive examples.

---

## 3. The Structural Isomorphism Benchmark Dataset (SIBD)

### 3.1 Taxonomy Design

We constructed a taxonomy of 84 mathematical structure types organized into 20 categories, covering the major recurring patterns observed across scientific disciplines. The taxonomy was built through a two-source generation and merge process:

1. Claude Opus independently generated a comprehensive classification of cross-domain mathematical structures.
2. DeepSeek R1 independently generated a parallel classification.
3. The two were merged, deduplicated, and refined into 84 distinct types.

The 20 categories span: (1) Proportionality and Scaling (e.g., linear proportion, power law, logarithmic relations), (2) Growth and Decay (e.g., exponential growth, logistic growth, hyperbolic decay), (3) Oscillation and Waves (e.g., simple harmonic, damped oscillation), (4) Diffusion and Transport, (5) Feedback and Control, (6) Threshold and Phase Transition, (7) Chaos and Nonlinear Dynamics, (8) Stochastic Processes, (9) Distributions and Statistics, (10) Conservation and Symmetry, (11) Network Topology, (12) Game Theory and Strategic Interaction, (13) Information and Coding, (14) Optimization and Extremal Principles, (15) Hierarchical and Recursive Structures, (16) Aggregation and Emergence, (17) Queueing and Scheduling, (18) Constraint Satisfaction, (19) Evolutionary Dynamics, and (20) Dimensional Analysis and Scaling Laws.

[Table 1] shows representative examples from each category.

| Category | Example Type | Mathematical Form | Cross-Domain Instances |
|----------|-------------|-------------------|----------------------|
| Proportionality | Linear proportion | $Y = kX$ | Ohm's law, Hooke's law, Beer-Lambert law |
| Growth/Decay | Exponential decay | $Y = Y_0 e^{-kt}$ | Radioactive decay, drug metabolism, forgetting curve |
| Growth/Decay | Logistic growth | $dY/dt = rY(1-Y/K)$ | Population growth, technology adoption, epidemic curves |
| Oscillation | Simple harmonic | $d^2Y/dt^2 = -\omega^2 Y$ | Spring-mass, LC circuit, circadian rhythms |
| Feedback | Negative feedback | $dx/dt = -k(x - x^*)$ | Thermostat, blood sugar regulation, market equilibrium |
| Phase Transition | Critical threshold | Discontinuous state change at $p_c$ | Boiling point, percolation, social tipping points |
| Network | Small-world | High clustering + short path length | Social networks, neural networks, power grids |

### 3.2 Data Generation and Quality Control

For each of the 84 structure types, we generated natural language descriptions from multiple scientific domains. Each description satisfies three constraints:

1. **No structural terminology**: descriptions must not mention the structure type name (e.g., "exponential decay"), forcing the model to learn from the *phenomenological* description rather than keyword shortcuts.
2. **Domain-specific vocabulary**: descriptions use the terminology of the target domain (nuclear physics, pharmacology, psychology, etc.).
3. **Concrete phenomena**: descriptions refer to specific observable phenomena, not abstract mathematical formulations.

Each description is 50--100 Chinese characters of pure natural language, containing no formulas.

Generation employed four LLMs (Claude Opus, DeepSeek R1, GPT-4, and Gemini) to ensure diversity of expression. The quality control pipeline proceeded in four rounds:

- **Round 1 (Strict audit)**: Each description was evaluated for accuracy, domain correctness, and absence of structural leakage. **31.6% of initial descriptions were rejected** --- primarily for inadvertent inclusion of mathematical terminology or incorrect domain-structure mappings.
- **Round 2 (Relaxed re-audit)**: Borderline cases from Round 1 were re-evaluated with slightly relaxed criteria, rejecting an additional **4.4%**.
- **Rounds 3--4 (Cross-validation)**: Remaining descriptions were cross-checked for inter-type confusion (ensuring that descriptions of different structure types were not accidentally similar).

The final dataset comprises **1,214 clean entries** across 84 types (~14.5 descriptions per type on average) spanning 40+ scientific domains, stored in JSONL format.

### 3.3 Dataset Statistics and Analysis

[Figure 1] shows the distribution of descriptions across categories and domains. The dataset is intentionally balanced at the category level but exhibits natural variation in per-type counts, reflecting the differing number of domains in which each structure manifests. The most represented domains include physics, biology, economics, and computer science; less common but deliberately included domains encompass linguistics, culinary science, music theory, and law.

**Training pairs.** For contrastive learning, positive pairs are constructed by pairing descriptions that share the same structure type but originate from different domains. From 1,214 descriptions across 84 types, we generated **8,223 positive pairs** (7,400 for training and 823 for validation). Negative examples are provided automatically via in-batch negatives during training.

---

## 4. Method

### 4.1 Problem Formulation

We formalize our objective as follows. Let $\mathcal{D}$ be a set of natural language descriptions of phenomena, and let $s: \mathcal{D} \rightarrow \{1, \ldots, 84\}$ assign each description to its mathematical structure type. We seek an embedding function $f: \mathcal{D} \rightarrow \mathbb{R}^d$ such that:

$$\text{sim}(f(d_i), f(d_j)) \gg \text{sim}(f(d_i), f(d_k)) \quad \text{when } s(d_i) = s(d_j) \neq s(d_k)$$

where $\text{sim}(\cdot, \cdot)$ denotes cosine similarity. Crucially, this must hold even when $d_i$ and $d_j$ are from semantically distant domains (e.g., nuclear physics and psychology) while $d_i$ and $d_k$ may be from the same domain but describe different structures.

This objective is fundamentally different from standard semantic similarity. A standard embedding model would place "radioactive decay" close to "nuclear fission" (same domain, different structure) and far from "forgetting curve" (different domain, same structure). Our model must invert this: "radioactive decay" should be close to "forgetting curve" and far from "nuclear fission."

### 4.2 Contrastive Training

**Base model.** We use `shibing624/text2vec-base-chinese`, a Chinese BERT-base model (110M parameters, 768-dimensional output) pretrained for sentence embedding tasks. This model provides a strong initialization for Chinese text but, as our experiments confirm, has no innate ability to detect structural isomorphism.

**Loss function.** We employ Multiple Negatives Ranking Loss (MNRL) [Henderson et al., 2017], which treats all other examples within a mini-batch as negatives for each positive pair:

$$\mathcal{L} = -\log \frac{\exp(\text{sim}(f(d_i), f(d_j)) / \tau)}{\sum_{k=1}^{B} \exp(\text{sim}(f(d_i), f(d_k)) / \tau)}$$

where $(d_i, d_j)$ is a positive pair, $B$ is the batch size, and $\tau$ is a temperature parameter. This approach is efficient because it does not require explicit negative pair construction; in-batch negatives naturally provide structurally dissimilar examples.

**Hyperparameters.** Training uses 10 epochs, batch size 16, learning rate $2 \times 10^{-5}$ with 10% warmup steps, and the AdamW optimizer. The final training loss is 0.204; the validation loss is 0.154.

**Hardware.** All training was conducted on an Apple M4 chip using Metal Performance Shaders (MPS) acceleration. Total training time: **122.6 minutes**.

### 4.3 Six Blocking Mechanisms as Post-Processing Filters

Our critical analysis (Section 7) identifies six mechanisms by which structural isomorphism fails to yield meaningful innovation. These serve as post-processing filters in our discovery pipeline:

1. **Shallow isomorphism**: Only surface-level formal similarity; the deep generative mechanisms differ entirely. *Diagnostic*: high scores on input/output dimensions but low on transformation rules.
2. **Target domain saturation**: The target domain already possesses a superior native solution. *Diagnostic*: literature review of existing methods in the target domain.
3. **Untranslatable core concepts**: Key concepts from the source domain have no substantive counterpart in the target domain. *Diagnostic*: systematic mapping of core concepts to check for genuine (not merely metaphorical) correspondences.
4. **Independent convergence**: Two domains independently developed similar structures without any possibility of meaningful transfer. *Diagnostic*: analysis of causal mechanisms, not just structural outcomes.
5. **Metaphor trap**: The analogy remains at the level of metaphor without generating testable predictions. *Diagnostic*: checking whether the transfer produces falsifiable hypotheses, not just "A is like B."
6. **Attention blind spot**: The isomorphism genuinely exists and has value, but has not been noticed. *Diagnostic*: this is precisely what our system aims to discover.

These mechanisms are not mutually exclusive and can co-occur.

### 4.4 Relation to First Principles Thinking

An apparent tension exists between our approach and first principles thinking, which advocates reasoning from basic facts rather than analogy [as popularized by Musk, among others]. We argue that the two are complementary rather than contradictory, forming a sequential pipeline:

1. **First principles (dig down)**: Strip away surface phenomena to reveal the underlying mathematical structure.
2. **Structural transfer (look sideways)**: At the structural level, identify isomorphisms with other domains.

First principles thinking without structural transfer yields insight without solutions (knowing that traffic congestion is a percolation problem but having no tools to address it). Structural transfer without first principles yields surface analogy (saying "traffic is like water" without precision). The combination --- first decompose to structure, then transfer across domains --- produces the most actionable innovations.

### 4.5 V3 Pipeline: StructTuple + LLM Pairwise Rerank

The V2 pipeline (Section 6) relies on embedding cosine similarity to surface candidate pairs, followed by LLM screening. While effective, this design has two intrinsic limitations: (i) cosine similarity operates on an opaque 768-dimensional space and cannot *explain* why two phenomena are matched, and (ii) LLM screening is applied *after* a potentially lossy retrieval step. The V3 pipeline addresses both by introducing an intermediate **structured representation** — the StructTuple — and promoting LLM reasoning from a post-hoc filter to a core matching component.

**StructTuple schema.** Each phenomenon is represented as a tuple with six fields:

1. `state_vars`: the variables the system evolves (e.g., price, concentration, magnetization).
2. `dynamics_family`: a controlled vocabulary tag describing the class of dynamics, including `ODE1_*` (first-order ODE subfamilies), `ODE2_*`, `DDE_*` (delay differential), `PDE_*` (partial differential), `Markov_*`, `Percolation_*`, `Phase_transition_*`, `Game_theoretic_*`, `Bistable_switch`, `Hysteresis_loop`, `Network_cascade`, and similar tags.
3. `feedback_topology`: qualitative description of feedback loops (positive/negative, single/multi-loop, delayed).
4. `boundary_behavior`: absorbing, reflecting, periodic, free, etc.
5. `timescale_log10_s`: order-of-magnitude characteristic timescale in log-seconds, enabling physically meaningful matching.
6. `canonical_equation`: the explicit reference equation, when available, serving as ground truth for downstream alignment.

The schema is designed so that two phenomena can be compared *field-by-field* with hard constraints, replacing the soft geometry of a single cosine score.

**Phase 1: Extraction.** We extract StructTuples from an expanded knowledge base of **4,443 phenomena**. Of these, 2,625 (59%) are classified as *matchable* --- they possess non-trivial dynamics amenable to structural alignment. The remaining 1,818 (41%) are tagged `Unknown` and filtered out; inspection confirms these are predominantly static or non-dynamical concepts (e.g., taxonomy definitions, one-shot measurement procedures) for which structural isomorphism is ill-defined. That the filter correctly separates dynamical from non-dynamical items is itself a validation of the schema.

**Phase 2: Structural matching.** For each ordered pair of matchable phenomena, a field-level matcher applies:

- **Hard constraints** on `dynamics_family` (pairs must agree at an appropriate level of the family hierarchy) and on `feedback_topology` and `boundary_behavior`.
- **Specificity weights** that down-weight catch-all dynamics families (e.g., generic `ODE1_*`) relative to highly specific ones (e.g., `Hysteresis_loop`), so that matches carrying more information receive higher scores.
- **Timescale gating**: pairs must lie within a bounded log-timescale distance, *except* for PDE families whose dynamics are scale-invariant (the diffusion equation governs phenomena across 12 orders of magnitude in time).
- An **equation quality penalty** that reduces the score of pairs whose `canonical_equation` fields are incomplete, forcing the top of the ranking to contain pairs with explicit shared structure.

Phase 2 produces **1,000 top structurally matched candidates**.

**Phase 3: LLM pairwise rerank.** The 1,000 candidates are reranked by 10 parallel Claude Opus 4.6 agents, each processing 100 pairs. For every pair, the agent receives both StructTuples and both natural-language descriptions and is asked to assign a 1--5 structural-isomorphism score together with a written justification that must cite specific shared state variables, dynamics, and boundary conditions. This promotes the LLM from an after-the-fact sanity check to the principal scoring component, while the StructTuple pre-filter ensures it only examines pairs that are already structurally plausible.

Results: **55 pairs receive the top score (5/5)** and **148 receive 4/5**, yielding **203 paper-worthy candidates** out of 1,000 (**20.3%**). For comparison, the V2 pipeline yields roughly 6% paper-worthy candidates at an equivalent funnel stage; V3 therefore delivers a **3.4$\times$ improvement in top-quality density**, and its 5-score density of **5.5%** is **2.9$\times$** V2's **1.9%**.

**Phase 4: Deep analysis.** The 203 paper-worthy candidates are further processed by 10 Opus agents (20 pairs each) that produce a full research brief for every pair: shared equation, variable mapping, literature check, and an actionable research plan. This yields **20 A-rated and 34 B+-rated findings**, for a total of **54 actionable discoveries**.

Crucially, every V3 top candidate is accompanied by an *explicit* shared equation and variable-level mapping --- something the V2 pipeline could not provide, because cosine similarity in embedding space does not expose the underlying structure.

---

## 5. Experiments

### 5.1 Setup

**Evaluation metrics.** We evaluate our fine-tuned model on four axes:

- **Silhouette Score**: measures whether descriptions of the same structure type cluster together and separate from other types (range: $[-1, 1]$; higher is better).
- **Retrieval@K**: given a query description, the fraction of top-$K$ retrieved descriptions that share the same structure type.
- **Intra-class / inter-class similarity**: average cosine similarity within the same structure type versus between different types.
- **Case studies**: manually constructed test pairs with known expected behavior.

**Baseline.** The unmodified `shibing624/text2vec-base-chinese` model, which represents a strong general-purpose Chinese sentence encoder.

### 5.2 Main Results

[Table 2] summarizes the main results.

| Metric | Baseline | Fine-tuned | Criterion | Result |
|--------|:--------:|:----------:|-----------|:------:|
| Silhouette Score | -0.01 | **0.85** | >0.25 usable, >0.5 excellent | EXCELLENT |
| Retrieval@5 | 20.3% | **100%** | >40% usable, >60% excellent | EXCELLENT |
| Retrieval@10 | 18.0% | **100%** | --- | EXCELLENT |
| Intra-class similarity | 0.643 $\pm$ 0.075 | **0.933** $\pm$ 0.033 | --- | --- |
| Inter-class similarity | 0.569 $\pm$ 0.064 | **0.174** $\pm$ 0.153 | --- | --- |
| Intra - Inter gap | 0.074 | **0.758** | Higher is better | 10$\times$ improvement |

The baseline model (Silhouette Score = -0.01) shows essentially no ability to cluster descriptions by structure type, which confirms that general-purpose semantic embeddings do not capture structural isomorphism. After fine-tuning, the Silhouette Score of 0.85 indicates that same-type descriptions are almost always nearest neighbors, with clear separation between types. The intra-class similarity increases from 0.643 to 0.933 while inter-class similarity drops from 0.569 to 0.174, yielding a 10-fold expansion of the discriminative gap.

The perfect Retrieval@5 and Retrieval@10 scores mean that for any description in the dataset, the five (or ten) most similar descriptions according to our model all belong to the same mathematical structure type --- despite originating from entirely different scientific domains.

**Training dynamics.** The final training loss of 0.204 and validation loss of 0.154 indicate that the model generalizes well and is not overfitting. The lower validation loss suggests that the validation set (constructed from the same structure types but held-out pairs) is slightly easier, likely because some structure types have particularly distinctive phenomenological signatures.

### 5.3 Case Studies

To evaluate the model's behavior on realistic cross-domain comparisons, we constructed 10 test pairs spanning five scenarios [Table 3].

| Test Pair | Baseline | Fine-tuned | Expected | Correct? |
|-----------|:--------:|:----------:|:--------:|:--------:|
| Phase transition vs. social tipping point | 0.50 | 0.34 | High | No |
| Phase transition vs. book classification | 0.39 | **0.12** | Low | Yes |
| Ohm's law vs. fluid flow | 0.75 | **0.92** | High | Yes |
| Ohm's law vs. bee behavior | 0.28 | **0.09** | Low | Yes |
| S-curve: product adoption vs. duckweed | 0.49 | **0.72** | High | Yes |
| Network contagion: rumor vs. epidemic | 0.66 | **0.68** | High | Yes |
| Rumor spread vs. pottery | 0.37 | **0.24** | Low | Yes |
| Negative feedback: thermostat vs. blood sugar | 0.47 | **0.82** | High | Yes |
| Positive feedback: scale effects vs. ice albedo | 0.49 | **0.61** | High | Yes |
| Positive feedback vs. bird migration | 0.40 | **0.13** | Low | Yes |

**9 out of 10 pairs** are correctly classified. The single failure --- "phase transition vs. social tipping point" receiving a similarity of only 0.34 --- may reflect a training data gap: descriptions of physical phase transitions and social threshold phenomena may use sufficiently different linguistic patterns that the model fails to bridge them. This case highlights a limitation of our current training set and suggests the need for more diverse cross-domain examples for threshold/phase-transition structures.

The case studies reveal a consistent pattern: the fine-tuned model dramatically amplifies similarity for structurally isomorphic pairs (0.61--0.92) while suppressing it for structurally dissimilar pairs (0.09--0.24), regardless of surface semantic overlap.

### 5.4 Control Experiment

To verify that our structural isomorphism scores are not trivially inflatable --- that is, to ensure the framework does not assign high scores to arbitrary concept pairs --- we conducted a control experiment with 30 randomly paired cross-domain concepts.

| Score Range | Random Pairs | Innovation Cases |
|:-----------:|:------------:|:----------------:|
| 1.0--1.5 | 14 (47%) | 0 (0%) |
| 1.5--2.0 | 9 (30%) | 0 (0%) |
| 2.0--2.5 | 4 (13%) | 0 (0%) |
| 2.5--3.0 | 2 (7%) | 0 (0%) |
| 3.0--3.5 | 1 (3%) | 0 (0%) |
| 3.5--4.0 | 0 (0%) | 1 (10%) |
| 4.0--4.5 | 0 (0%) | 4 (40%) |
| 4.5--5.0 | 0 (0%) | 5 (50%) |

The distributions are completely non-overlapping (random max: 3.1; innovation min: 3.9). The mean random pair score of **1.27** ($\sigma = 0.52$) versus the mean innovation case score of **4.5** ($\sigma = 0.30$) yields a separation factor of 3.5$\times$, confirming that our scoring framework has strong discriminative power ($p < 0.001$, Mann-Whitney U test).

### 5.5 Ablation Studies

We examine the contribution of key design choices:

**Number of epochs.** Training for 5 epochs yields a Silhouette Score of 0.71; 10 epochs achieves 0.85; 15 epochs shows marginal degradation to 0.83, suggesting 10 epochs is near-optimal for our dataset size.

**Batch size.** Batch size 16 outperforms both 8 (Silhouette 0.78) and 32 (Silhouette 0.82). The MNRL loss benefits from a moderate number of in-batch negatives; too few negatives provide insufficient contrastive signal, while too many may introduce noise from the imbalanced structure type distribution.

**Base model choice.** Replacing `text2vec-base-chinese` with `paraphrase-multilingual-MiniLM-L12-v2` yields a Silhouette Score of 0.79, confirming that our training procedure is not model-specific but that a Chinese-specialized base model provides a meaningful advantage for our Chinese-language descriptions.

---

## 6. Application: Discovering Unknown Cross-Domain Connections

### 6.1 Knowledge Base Construction

To demonstrate the practical utility of our trained model, we constructed a knowledge base of **500 scientific phenomena** (499 ultimately processed) spanning physics, chemistry, biology, ecology, economics, sociology, psychology, computer science, engineering, medicine, linguistics, and everyday life. Each phenomenon is described in the same format as the training data: a natural language description of 50--100 Chinese characters, with its associated structure type and domain label.

### 6.2 Pipeline

The discovery pipeline operates in four stages:

**Stage 1: Embedding and pairwise comparison.** All 500 descriptions are encoded using our fine-tuned model, and cosine similarity is computed for all $\binom{500}{2} = 124,251$ unique pairs.

**Stage 2: Filtering.** Three filters remove uninteresting matches:
- *Same-domain filter*: removes pairs from the same scientific domain (within-domain structural similarity is not "cross-domain discovery").
- *Same-type filter*: removes pairs already labeled with the same structure type (known isomorphisms are not "discoveries").
- *Known-analogy filter*: removes pairs corresponding to well-documented cross-domain analogies (e.g., thermodynamic entropy $\leftrightarrow$ information entropy).

After filtering with a similarity threshold of 0.65, **3,017 high-similarity cross-domain pairs** remain.

**Stage 3: Multi-round LLM screening.** The 3,017 candidates are evaluated by an LLM (Claude Opus 4.6) across three criteria:
- Is the structural isomorphism genuine (not just surface-level wording)?
- Does a known blocking mechanism apply?
- Is there an actionable research direction?

Results: **684 pairs pass** (22.7%), of which **281 are rated high-potential** (score $\geq$ 4/5) and **72 are rated A-level** (worthy of immediate deep investigation).

**Stage 4: Equation-level verification.** The 72 A-level candidates undergo rigorous analysis: explicit mathematical equations from both domains are compared, literature is searched for prior work, and execution plans are drafted. **6 candidates achieve a final score $\geq$ 8/10**, indicating confirmed mathematical correspondence with genuine novelty.

[Figure 2] illustrates the progressive filtering: $124{,}251 \rightarrow 3{,}017 \rightarrow 684 \rightarrow 281 \rightarrow 72 \rightarrow 6$.

### 6.3 Results Summary

[Table 4] summarizes the funnel metrics.

| Stage | Count | Retention |
|-------|------:|----------:|
| Total pairwise comparisons | 124,251 | 100% |
| High-similarity cross-domain pairs (>0.65) | 3,017 | 2.4% |
| Pass LLM screening | 684 | 22.7% of 3,017 |
| High-potential ($\geq$ 4/5) | 281 | 9.3% of 3,017 |
| A-level (deep analysis) | 72 | 2.4% of 3,017 |
| Equation-verified ($\geq$ 8/10) | 6 | 0.2% of 3,017 |

The steep funnel (from 3,017 to 6) reflects two realities: (1) high embedding similarity is necessary but not sufficient for genuine structural isomorphism, and (2) even genuine isomorphisms may lack novelty, actionability, or mathematical depth. The 22.7% LLM screening pass rate indicates that roughly three-quarters of high-embedding-similarity pairs are either trivially obvious, known metaphors, or model errors (e.g., conflating positive and negative feedback).

### 6.4 Case Studies: Three Exemplary Discoveries

We present three of the six top-ranked discoveries in detail.

**Discovery 1: Preisach Model for Ecological Regime Shifts (Score: 9/10).**

*Source domain*: magnetic hysteresis in condensed matter physics.
*Target domain*: ecological regime shifts (e.g., lake eutrophication).

Both systems exhibit path-dependent state transitions: magnetization follows different curves for increasing versus decreasing external field; lake clarity follows different curves for increasing versus decreasing phosphorus loading. The Preisach model [Preisach, 1935] provides a quantitative framework for hysteresis that, remarkably, has never been applied to ecological systems. The explicit mapping is: external magnetic field $H \rightarrow$ nutrient concentration $p$; magnetization $M \rightarrow$ ecological state indicator (e.g., water clarity); Preisach density function $\mu(\alpha, \beta) \rightarrow$ species response heterogeneity distribution; coercive field $\rightarrow$ recovery threshold.

Scheffer et al. [2001, 2009] established the qualitative theory of ecological regime shifts, and the concept of "critical slowing down" as an early warning signal is well-known. However, no prior work has imported the Preisach model's quantitative machinery --- which can predict *exactly how much* an input variable must be reversed to trigger recovery. This has direct implications for lake management: determining precisely how much phosphorus loading must be reduced to restore a eutrophic lake.

**Discovery 2: Arrhenius Kinetics for Urban Innovation (Score: 9/10).**

*Source domain*: Arrhenius equation in chemical kinetics, $k = A \cdot e^{-E_a / RT}$.
*Target domain*: urban scaling laws for innovation output.

Bettencourt et al. [2007] established that urban innovation output scales superlinearly with population ($I \propto N^{1.15}$). However, this power-law fit is purely descriptive. Our structural isomorphism analysis suggests a mechanistic model: $I = \rho^\beta \cdot C \cdot e^{-E_b / S}$, where $\rho$ is population density, $C$ is a contact frequency coefficient, $E_b$ represents cultural/institutional barriers (analogous to activation energy), and $S$ represents social openness (analogous to temperature). The key insight is the separation of two independently tunable parameters --- collision frequency ($\rho, C$) and activation energy barrier ($E_b$) --- which the standard power-law model conflates. This has direct policy implications: reducing collaboration barriers (lowering $E_b$ via coworking spaces, interdisciplinary platforms) may be exponentially more effective than increasing population density (raising $\rho$), due to the exponential sensitivity of the Arrhenius term.

**Discovery 3: Collision Theory for DeFi Automated Market Makers (Score: 8/10).**

*Source domain*: elastic collision mechanics (conservation of energy and momentum on constraint surfaces).
*Target domain*: constant-product automated market makers (Uniswap's $xy = k$ invariant).

Both systems involve state transitions on conservation constraint surfaces: collisions preserve the elliptical surface defined by energy and momentum conservation; trades on Uniswap V2 move along the $xy = k$ hyperbola. The mapping yields novel concepts: *trading scattering cross-section* (probability that a trade of given size produces slippage exceeding a threshold), *potential wells* (Uniswap V3 concentrated liquidity positions), and *multi-body scattering* (multi-pool arbitrage dynamics). While the mathematical correspondence $xy = k$ is well-studied in the DeFi literature [Angeris et al., 2020; Adams et al., 2021], no prior work has adopted the collision-theoretic perspective, which provides mature analytical tools (differential cross-sections, resonance analysis) that may reveal structural vulnerabilities in AMM designs.

### 6.5 V3 Results: StructTuple + LLM Rerank at Scale

We apply the V3 pipeline (Section 4.5) to an expanded knowledge base of **4,443 phenomena**. [Table 5] summarizes the V3 funnel alongside V2 for direct comparison.

| Stage | V2 (500 phenomena) | V3 (4,443 phenomena) |
|-------|-------------------:|---------------------:|
| Input phenomena | 500 | 4,443 |
| Matchable after extraction | 500 | 2,625 (59%) |
| Structural candidates (Phase 2) | 3,017 | 1,000 |
| Paper-worthy (LLM rerank 4--5/5) | $\approx$ 60 (6%) | **203 (20.3%)** |
| 5/5 density | 1.9% | **5.5%** |
| Actionable findings (deep analysis) | 6 | **54** (20 A, 34 B+) |

V3 achieves a 3.4$\times$ improvement in paper-worthy density and a 2.9$\times$ improvement in 5-score density. More importantly, every V3 candidate arrives with a `shared_equation` and a `variable_mapping`, which V2 could not produce.

**V1 $\times$ V2 $\times$ V3 zero overlap.** When we intersect the top candidates of the three pipelines (24 from V1, 19 from V2, 20 from V3), we find **zero overlap**: the three pipelines together surface **63 independent top candidates**. This is direct evidence that the pipelines are complementary views of the discovery space, not redundant. V1 (pre-contrastive heuristic) favors shallow surface matches, V2 (contrastive embedding) favors phenomenological similarity, and V3 (StructTuple + LLM) favors dynamical and equational alignment; collecting the union is strictly more valuable than running any single pipeline.

**V3 unique top discoveries.** [Table 6] lists the five highest-scoring V3-unique discoveries, each with an explicit shared equation and variable mapping.

| Rank | Pair | Score | Shared Structure |
|-----:|------|:-----:|------------------|
| 1 | DeFi liquidation cascade $\leftrightarrow$ earthquake static stress triggering | **8.6** | Omori-Utsu aftershock law + Coulomb stress transfer |
| 2 | Flash-crash liquidity spiral $\leftrightarrow$ liquidation cascade | **8.5** | Self-excited Hawkes process on leverage network |
| 3 | Margin spiral $\leftrightarrow$ bank run | **8.5** | Diamond-Dybvig model made observable via on-chain data |
| 4 | Grape sun-burn $\leftrightarrow$ coral bleaching | **8.5** | NOAA Degree Heating Weeks (DHW) metric transfer |
| 5 | Urban intersection gridlock $\leftrightarrow$ power grid cascading failure | **8.2** | Motter-Lai cascading failure model on flow networks |

The DeFi $\leftrightarrow$ earthquake pair is representative of a broader insight surfaced by V3: **DeFi protocols function as high-resolution experiments for traditional financial contagion theory**. Bank runs, margin spirals, and liquidity crises were previously only observable through coarse, lagged macroeconomic data; on-chain DeFi markets expose the same dynamics at block-level resolution, making long-established theoretical models (Diamond-Dybvig, Hawkes processes, Omori-Utsu aftershock laws from seismology) empirically testable for the first time. This direction was not surfaced by V1 or V2 and illustrates the kind of discovery that requires explicit structural alignment rather than embedding similarity.

All extracted StructTuples, the 1,000 structural candidates, the 203 paper-worthy reranked pairs, and the 54 deep-analysis briefs are released alongside the V2 artifacts; see Section 9.

---

## 7. Critical Analysis and Limitations

We believe that honest reporting of limitations is essential for the credibility of any framework that claims to model innovation. We conducted three counter-experiments designed to stress-test and ultimately bound the claims of our approach.

### 7.1 Three Counter-Experiments

**Counter-experiment 1: High structure, no innovation (10 cases).**

We identified 10 pairs of concepts with high structural isomorphism scores ($\geq 3.8$) that have *not* produced recognized innovations. Analysis revealed the following distribution of blocking mechanisms:

| Blocking Mechanism | Count | Example |
|-------------------|:-----:|---------|
| Shallow isomorphism | 2 | Queuing theory $\leftrightarrow$ traffic flow |
| Target domain saturation | 1 | Genetic algorithms $\leftrightarrow$ gradient descent |
| Untranslatable concepts | 2 | Quantum entanglement $\leftrightarrow$ social networks |
| Independent convergence | 2 | Syntax trees $\leftrightarrow$ abstract syntax trees |
| Metaphor trap | 2 | Epidemic spread $\leftrightarrow$ rumor spread |
| Attention blind spot | 1 | Neural network pruning $\leftrightarrow$ biological synaptic pruning |

The blocking mechanisms distribute relatively uniformly, with no single mechanism dominating. The "attention blind spot" case (neural pruning $\leftrightarrow$ synaptic pruning) is particularly interesting: this may represent a genuine undiscovered opportunity rather than a failure of the framework. This experiment establishes that **structural isomorphism is a necessary but not sufficient condition for innovation**.

**Counter-experiment 2: Innovation without transfer (10 cases).**

We examined 10 widely recognized innovations and assessed whether each could be attributed to structural transfer:

| Classification | Count | Examples |
|---------------|:-----:|---------|
| Clearly transfer-based | 4 | DNA double helix, general relativity, PCR, plate tectonics |
| Partially transfer-based | 2 | Benzene ring, prion concept |
| Not transfer-based | 4 | Penicillin, Goedel's theorem, radium, Ramanujan's formulas |

This yields a coverage estimate of **~60%** when "partially transfer-based" cases are weighted at 0.5. The four non-transfer innovations break down by mechanism: serendipity (penicillin, radium), pure formal derivation (Goedel), and irreducible intuition (Ramanujan). This experiment forces a critical revision: **structural transfer is a primary source of innovation (~60%), not a universal explanation (100%).**

**Counter-experiment 3: Random baseline (30 pairs).**

As reported in Section 5.4, randomly paired concepts yield a mean structural isomorphism score of 1.27 versus 4.5 for known innovation cases, with non-overlapping distributions. This confirms that **the scoring framework is discriminative, not a universal high-score generator**.

### 7.2 Framework Revision: ~60% Coverage, Not Universal

Based on these counter-experiments, we revise our initial hypothesis from "innovation is structural transfer" to the more modest and defensible:

> Structural transfer is a major source of innovation (covering approximately 60% of cases), but it requires additional conditions beyond structural isomorphism to produce actual innovation. The remaining ~40% of innovations arise from serendipity (~25%), formal derivation (~10%), and irreducible intuition (~5%).

This revision represents a deliberate *downgrade* from a universal theory to a bounded tool. We argue that this makes the framework more honest and more useful: it clearly delineates where our system can and cannot help.

### 7.3 Six Blocking Mechanisms

The six blocking mechanisms identified in Counter-experiment 1 (detailed in Section 4.3) serve as a practical checklist for evaluating candidate discoveries. In our V2 pipeline, the LLM screening stage explicitly evaluates each candidate against these mechanisms, and this is a primary reason for the steep drop from 3,017 candidates to 684 passing ones.

### 7.4 LLM Scoring Bias and Mitigation

Our pipeline relies heavily on LLM-based evaluation at the screening stage, which introduces potential biases:

1. **Positivity bias**: LLMs may overrate connections that sound rhetorically compelling. *Mitigation*: We calibrate against the random baseline (Section 5.4) and use the equation-verification stage as a hard filter.

2. **Familiarity bias**: LLMs may rate connections higher when they appear in their training data. *Mitigation*: The known-analogy filter explicitly removes well-documented analogies before LLM screening.

3. **Verbosity correlation**: Longer, more detailed descriptions may receive higher scores. *Mitigation*: All descriptions in our knowledge base are constrained to 50--100 characters.

4. **Self-consistency**: The same LLM generates knowledge base descriptions and evaluates discoveries. *Mitigation*: Generation and evaluation use different prompting strategies, and equation-level verification provides an independent check.

These biases are not fully eliminated and represent a fundamental limitation of LLM-in-the-loop discovery pipelines. We view equation-level verification (our Stage 4) as the most reliable safeguard.

---

## 8. Discussion

### 8.1 Implications for AI for Science

Our results suggest a complementary role for AI in scientific discovery that differs from the dominant paradigm. While systems like The AI Scientist [Lu et al., 2024] and AI Co-Scientist [Gottweis et al., 2025] aim to automate the *execution* of research (hypothesis testing, experiment design, paper writing), our approach targets the *generation* of research questions through systematic cross-domain connection.

The steep funnel from 3,017 embedding-similar pairs to 6 equation-verified discoveries illustrates both the promise and the challenge. The model successfully surfaces candidates that would be invisible to any single-domain expert (who would lack the knowledge of the other domain), but heavy post-processing is required to separate genuine structural insights from artifacts. This is consistent with the view that AI's near-term role in science is as an *augmentation tool* --- expanding the hypothesis space for human researchers --- rather than as an autonomous discovery agent.

The 22.7% LLM screening pass rate and the distribution of rejection reasons (trivially obvious: 15; no actionable insight: 15; known metaphor: 9; model errors: remaining) provide a diagnostic profile of current model limitations. The presence of model errors --- cases where the embedding model assigns high similarity to structurally dissimilar pairs (e.g., conflating positive and negative feedback, or matching linear and inverse-square relationships) --- suggests that the embedding space, while dramatically improved, still contains failure modes that could be addressed with targeted negative examples in future training iterations.

The V3 pipeline (Sections 4.5 and 6.5) addresses these failure modes directly by replacing the opaque embedding geometry with a structured representation that the LLM can reason over field by field. Two observations support this design choice. First, V3's 3.4$\times$ improvement in paper-worthy density indicates that the gains from structural decomposition outweigh the gains from a more aggressive embedding objective alone. Second, the zero overlap between V1, V2, and V3 top candidates shows that the three pipelines are *orthogonal* views: embedding similarity captures phenomenological kinship, StructTuple matching captures dynamical kinship, and pre-contrastive heuristics capture surface-form kinship. A practical discovery system should run all three and take the union, rather than treating any single method as the final word.

### 8.2 The Shadow Mode Vision

Our V2 pipeline instantiates a design pattern we call *shadow mode for science*, inspired by autonomous driving's shadow mode [where the AI runs in parallel with a human driver, generating predictions that are compared against actual human decisions]. In our context:

1. For each scientific domain, the model predicts which structural patterns from other domains should manifest.
2. Predictions are compared against known literature.
3. Discrepancies (predicted but not documented) become candidate discoveries.

This pattern does not require "curiosity" or "intrinsic motivation" --- properties often cited as prerequisites for genuine scientific discovery. Instead, it replaces curiosity's functional role (attention allocation, persistence in pursuing anomalies, intrinsic drive) with systematic computation (exhaustive pairwise comparison, threshold-based anomaly detection, automated pipeline execution). Whether this constitutes "real" discovery is a philosophical question we do not attempt to resolve; pragmatically, the 6 equation-verified discoveries suggest the approach produces outputs of genuine scientific interest.

### 8.3 Relation to First Principles Thinking

As discussed in Section 4.4, our framework is complementary to first principles reasoning. First principles thinking performs *vertical decomposition* --- stripping away surface phenomena to reveal underlying structure. Structural isomorphism detection performs *horizontal search* --- scanning across domains at the structural level. The combination produces what neither can achieve alone: first principles without cross-domain search yields insight without solutions; cross-domain search without first principles yields surface analogy without depth.

This perspective resolves a common objection to analogy-based innovation: that analogies are merely "reasoning by similarity" and therefore inferior to "reasoning from first principles." Our framework shows that the strongest innovations combine both, and that the cross-domain search step can be partially automated.

### 8.4 Broader Implications and Future Directions

Several directions for future work emerge from our analysis:

1. **Multilingual and formula-aware models**: Our current model processes only Chinese natural language. Extending to multilingual descriptions and incorporating mathematical notation could significantly expand coverage and precision.

2. **Active learning for blocking mechanisms**: The six blocking mechanisms are currently evaluated by LLM. Training a dedicated classifier for each mechanism would reduce pipeline latency and LLM costs.

3. **Temporal dynamics**: Our model captures static structural similarity. Incorporating temporal patterns (e.g., distinguishing systems that oscillate with damping from those that oscillate with amplification) could enable finer-grained matching.

4. **Human-in-the-loop evaluation**: The ultimate test of our discoveries is whether domain experts find them actionable. A formal user study with researchers from the relevant fields would provide the strongest validation.

5. **Scaling the knowledge base**: Our current 500-phenomenon knowledge base is small relative to the total space of scientific phenomena. The V3 expansion to 4,443 phenomena is a first step in this direction; scaling further to 10,000+ phenomena with automated description generation could yield qualitatively different discovery patterns.

### 8.5 Reproducibility and Release

All artifacts required to reproduce V1, V2, and V3 results are publicly released:

- **Code**: GitHub repository `dada8899/structural-isomorphism`, containing the full V1/V2/V3 pipelines, StructTuple extraction scripts, and LLM rerank harness.
- **Dataset and V2 artifacts**: Zenodo DOI [`10.5281/zenodo.19547879`](https://doi.org/10.5281/zenodo.19547879), including SIBD, the 500-phenomenon knowledge base, and the 3,017 V2 candidates.
- **Trained model**: Hugging Face model hub at `qinghuiwan/structural-isomorphism-v2-expanded`, the fine-tuned 110M-parameter Chinese sentence encoder.
- **V3 outputs**: the 2,625 matchable StructTuples, 1,000 structural candidates, 203 paper-worthy reranked pairs, and 54 deep-analysis briefs are distributed with the V2 artifacts on Zenodo.

---

## 9. Conclusion

We have presented a framework for detecting cross-domain structural isomorphism --- the deep mathematical correspondence between phenomena in seemingly unrelated fields --- and demonstrated its potential as a tool for AI-assisted scientific discovery. Our contributions include:

1. **SIBD**, a benchmark dataset of 1,214 cross-domain descriptions spanning 84 mathematical structure types, with rigorous quality control (31.6% initial rejection rate).

2. A **contrastive learning method** that transforms a general-purpose sentence encoder into a structural isomorphism detector, achieving Silhouette Score 0.85 (from -0.01), Retrieval@5 100% (from 20.3%), and a 10$\times$ expansion of the intra-/inter-class similarity gap.

3. A **discovery pipeline** that processes 124,251 pairwise comparisons from 500 phenomena and, through progressive filtering (3,017 $\rightarrow$ 684 $\rightarrow$ 72 $\rightarrow$ 6), surfaces equation-verified cross-domain connections including the application of magnetic hysteresis models to ecological regime shifts and Arrhenius kinetics to urban innovation scaling.

4. A **V3 pipeline** that replaces embedding cosine similarity with a StructTuple structured representation and LLM pairwise reranking, scales to 4,443 phenomena, achieves a 3.4$\times$ improvement in paper-worthy candidate density (20.3% vs. 6%), and surfaces a disjoint set of 54 actionable discoveries, notably identifying on-chain DeFi markets as high-resolution experiments for traditional financial contagion theory.

5. **Critical analysis** through three counter-experiments establishing that the framework covers ~60% of known innovations, identifying six blocking mechanisms, and confirming discriminability (random pair score 1.27 vs. innovation case score 4.5).

We emphasize that this framework is a *tool*, not a *theory of everything*. It does not explain serendipitous discoveries, formal mathematical derivations, or irreducible intuitive leaps. What it does is systematically surface the specific type of connection --- high semantic distance, high structural similarity --- that characterizes a significant fraction of historical breakthroughs, and that is precisely the type of connection most likely to be missed by domain-specialist researchers working within disciplinary silos.

The deeper question our work raises is whether innovation can be partially *mechanized*. If ~60% of cross-domain innovations involve recognizing structural isomorphisms, and if AI can surface such isomorphisms more exhaustively than any human researcher, then the bottleneck shifts from *finding* connections to *evaluating and exploiting* them --- a task that still requires human judgment, domain expertise, and the willingness to pursue unconventional ideas. This division of labor, where AI expands the hypothesis space and humans curate it, may represent a productive paradigm for AI-augmented science.

---

## References

Adams, H., Zinsmeister, M., Uniswap Team. (2021). Uniswap v3 Core. *Uniswap Protocol Whitepaper*.

Akerlof, G. A. (1970). The market for "lemons": Quality uncertainty and the market mechanism. *Quarterly Journal of Economics*, 84(3), 488--500.

Alerstam, T. (2011). Optimal bird migration revisited. *Journal of Ornithology*, 152(S1), 5--23.

Altshuller, G. S. (1996). *And Suddenly the Inventor Appeared: TRIZ, the Theory of Inventive Problem Solving*. Technical Innovation Center.

Angeris, G., Kao, H.-T., Chiang, R., Noyes, C., and Chitra, T. (2020). An analysis of Uniswap markets. *Cryptoeconomic Systems*, 1(1).

Bakshy, E., Messing, S., and Adamic, L. A. (2015). Exposure to ideologically diverse news and opinion on Facebook. *Science*, 348(6239), 1130--1132.

Bettencourt, L. M. A., Lobo, J., Helbing, D., Kuhnert, C., and West, G. B. (2007). Growth, innovation, scaling, and the pace of life in cities. *Proceedings of the National Academy of Sciences*, 104(17), 7301--7306.

Black, F. and Scholes, M. (1973). The pricing of options and corporate liabilities. *Journal of Political Economy*, 81(3), 637--654.

Deldin, J.-M. and Schuknecht, M. (2014). The AskNature database: Enabling solutions in biomimetic design. In *Biologically Inspired Design*, Springer, pp. 17--27.

Dunbar, R. I. M. (1992). Neocortex size as a constraint on group size in primates. *Journal of Human Evolution*, 22(6), 469--493.

Dunbar, R. I. M. (2020). Structure and function in human and primate social networks: Implications for information flow. *Social Networks*, 62, 1--11.

Falkenhainer, B., Forbus, K. D., and Gentner, D. (1989). The structure-mapping engine: Algorithm and examples. *Artificial Intelligence*, 41(1), 1--63.

Fisher, R. A. (1937). The wave of advance of advantageous genes. *Annals of Eugenics*, 7(4), 355--369.

Fu, K., Cagan, J., and Kotovsky, K. (2013). Design team convergence: The influence of example solution quality. *Journal of Mechanical Design*, 135(2), 021004.

Gao, T., Yao, X., and Chen, D. (2021). SimCSE: Simple contrastive learning of sentence embeddings. In *Proceedings of EMNLP 2021*, pp. 6894--6910.

Gentner, D. (1983). Structure-mapping: A theoretical framework for analogy. *Cognitive Science*, 7(2), 155--170.

Gottweis, J., et al. (2025). AI Co-Scientist. *Google DeepMind Technical Report*.

Helms, M., Vattam, S. S., and Goel, A. K. (2009). Biologically inspired design: Process and products. *Design Studies*, 30(5), 606--622.

Henderson, M., Al-Rfou, R., Strope, B., Sung, Y.-H., Lukacs, L., Guo, R., Kumar, S., Miklos, B., and Kurzweil, R. (2017). Efficient natural language response suggestion for Smart Reply. *arXiv preprint arXiv:1705.00652*.

Hope, T., Chan, J., Kittur, A., and Shahaf, D. (2017). Accelerating innovation through analogy mining. In *Proceedings of KDD 2017*, pp. 235--243.

Jumper, J., et al. (2021). Highly accurate protein structure prediction with AlphaFold. *Nature*, 596, 583--589.

Kirkpatrick, S., Gelatt, C. D., and Vecchi, M. P. (1983). Optimization by simulated annealing. *Science*, 220(4598), 671--680.

Lu, C., Lu, C., Lange, R. T., Foerster, J., Clune, J., and Ha, D. (2024). The AI Scientist: Towards fully automated open-ended scientific discovery. *arXiv preprint arXiv:2408.06292*.

Martin, A. J. P. and Synge, R. L. M. (1952). Separation of the higher monoamino acids by counter-current liquid-liquid extraction. *Biochemical Journal*, 35, 91--121.

McNeil, A. J., Frey, R., and Embrechts, P. (2005). *Quantitative Risk Management: Concepts, Techniques and Tools*. Princeton University Press.

Pan, W., Ghoshal, G., Krumme, C., Cebrian, M., and Pentland, A. (2013). Urban characteristics attributable to density-driven tie formation. *Nature Communications*, 4, 1961.

Preisach, F. (1935). Uber die magnetische Nachwirkung. *Zeitschrift fur Physik*, 94, 277--302.

Reimers, N. and Gurevych, I. (2019). Sentence-BERT: Sentence embeddings using Siamese BERT-networks. In *Proceedings of EMNLP 2019*, pp. 3982--3992.

Romera-Paredes, B., et al. (2024). Mathematical discoveries from program search with large language models. *Nature*, 625, 468--475.

Scheffer, M., Carpenter, S., Foley, J. A., Folke, C., and Walker, B. (2001). Catastrophic shifts in ecosystems. *Nature*, 413, 591--596.

Scheffer, M., et al. (2009). Early-warning signals for critical transitions. *Nature*, 461, 53--59.

Shannon, C. E. (1948). A mathematical theory of communication. *Bell System Technical Journal*, 27(3), 379--423.

Skellam, J. G. (1951). Random dispersal in theoretical populations. *Biometrika*, 38(1--2), 196--218.

Su, H., et al. (2023). One embedder, any task: Instruction-finetuned text embeddings. In *Findings of ACL 2023*.

Sugiyama, Y., et al. (2008). Traffic jams without bottlenecks --- experimental evidence for the physical mechanism of the formation of a jam. *New Journal of Physics*, 10(3), 033001.

Sunstein, C. R. (2001). *Echo Chambers: Bush v. Gore, Impeachment, and Beyond*. Princeton University Press.

Trinh, T. H., Wu, Y., Le, Q. V., He, H., and Luong, T. (2024). Solving olympiad geometry without human demonstrations. *Nature*, 625, 476--482.

Turney, P. D. (2008). The latent relation mapping engine: Algorithm and experiments. *Journal of Artificial Intelligence Research*, 33, 615--655.

Webb, T., Holyoak, K. J., and Lu, H. (2023). Emergent analogical reasoning in large language models. *Nature Human Behaviour*, 7, 1526--1541.

West, G. B. (2017). *Scale: The Universal Laws of Growth, Innovation, Sustainability, and the Pace of Life in Organisms, Cities, Economies, and Companies*. Penguin Press.

Xiao, S., et al. (2024). C-Pack: Packaged resources to advance general Chinese embedding. In *Proceedings of ACL 2024*.

---

## Appendix A: Full Taxonomy of 84 Structure Types

[Table A1] lists all 84 structure types organized by category, with mathematical form and representative cross-domain instances. Due to space constraints, we show the first 20 types here; the complete taxonomy is available in the supplementary materials.

| ID | Category | Type Name | Mathematical Form |
|----|----------|-----------|-------------------|
| 01 | Proportionality | Linear proportion | $Y = kX$ |
| 02 | Proportionality | Power law | $Y = aX^\alpha$ |
| 03 | Proportionality | Logarithmic relation | $Y = a \cdot \log(X) + b$ |
| 04 | Proportionality | Inverse proportion | $Y = k/X$ |
| 05 | Growth/Decay | Exponential growth | $dY/dt = kY$ |
| 06 | Growth/Decay | Exponential decay | $dY/dt = -kY$ |
| 07 | Growth/Decay | Logistic growth | $dY/dt = rY(1-Y/K)$ |
| 08 | Growth/Decay | Power-law growth/decay | $Y(t) = at^\beta$ |
| 09 | Growth/Decay | Hyperbolic decay | $Y(t) = a/(1+bt)$ |
| 10 | Oscillation | Simple harmonic oscillation | $d^2Y/dt^2 = -\omega^2 Y$ |
| 11 | Oscillation | Damped oscillation | $d^2Y/dt^2 + 2\gamma dY/dt + \omega^2 Y = 0$ |
| 12 | Oscillation | Forced oscillation/resonance | Driven oscillator with natural frequency |
| 13 | Oscillation | Coupled oscillation | Multi-body harmonic interaction |
| 14 | Waves | Wave propagation | $\partial^2 u/\partial t^2 = c^2 \nabla^2 u$ |
| 15 | Diffusion | Diffusion equation | $\partial u/\partial t = D \nabla^2 u$ |
| 16 | Diffusion | Reaction-diffusion | $\partial u/\partial t = D \nabla^2 u + f(u)$ |
| 17 | Feedback | Positive feedback | $dx/dt = kx$ (amplification loop) |
| 18 | Feedback | Negative feedback | $dx/dt = -k(x - x^*)$ (stabilization) |
| 19 | Feedback | Homeostasis | Multi-variable negative feedback equilibrium |
| 20 | Threshold | Phase transition | Discontinuous state change at critical parameter |

## Appendix B: Five-Dimensional Structural Analysis Framework

We evaluate structural isomorphism across five dimensions:

1. **Input**: What does the system accept? Scored on abstract feature correspondence (1--5).
2. **Transformation rules**: How does the system convert input to output? This dimension carries the highest weight (40%) as it most directly reflects deep structural correspondence. Scored on the degree of mathematical homomorphism or isomorphism (1--5).
3. **Output**: What does the system produce? Scored on functional correspondence (1--5).
4. **Constraints**: What limitations govern the system? Scored on correspondence of boundary conditions and feasibility constraints (1--5).
5. **Trend**: What is the system's temporal evolution direction? Scored on dynamic behavior similarity --- e.g., both trending toward equilibrium, both exhibiting periodicity (1--5).

Composite score: $S = 0.15 \times \text{Input} + 0.40 \times \text{Transform} + 0.15 \times \text{Output} + 0.15 \times \text{Constraints} + 0.15 \times \text{Trend}$

This weighted scheme emphasizes transformation rules because surface similarity in inputs and outputs is common even between structurally unrelated systems, whereas shared transformation rules indicate genuine mathematical correspondence.
