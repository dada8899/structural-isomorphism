# Teaching a Neural Network to See Mathematical Skeletons: A Search Engine for Cross-Domain Structural Isomorphism

## The Question That Started Everything

It began with a late-night conversation about why AI hasn't discovered the next law of gravity.

Not the math part -- GPT-4 can solve differential equations. The hard part: noticing that an apple falling from a tree and the Moon orbiting Earth are *the same phenomenon*. Newton's breakthrough wasn't computation. It was structural recognition across a vast conceptual distance.

This led to a hypothesis: **scientific innovation is, at its core, long-distance structural transfer**. When someone notices that electrical circuits obey the same equations as fluid flow, or that epidemic spreading follows the same dynamics as information cascading through social networks, they are performing structural isomorphism detection. They are seeing through surface details to the mathematical skeleton underneath.

If that's true, then the bottleneck of cross-disciplinary discovery isn't intelligence. It's exposure. A physicist rarely reads ecology journals. An economist rarely studies fluid dynamics. The connections exist in the mathematics, but no one is looking.

We decided to build a system that looks.

## The Core Idea

The insight is simple: if two phenomena from different domains share the same mathematical structure, their natural-language descriptions should be *close* in some embedding space -- not because they use similar words, but because they describe similar relationships.

Standard text embeddings won't work. They cluster by topic: all ecology together, all physics together. We need an embedding that clusters by *structure*: all inverse-square laws together, all phase transitions together, all S-curves together, regardless of whether they describe gravitational attraction, Coulomb's law, or the brightness falloff of a light source.

So we built one.

## Method

### Building the Taxonomy

We started by cataloguing mathematical structures. Not equations per se, but structural *types*: power laws, exponential growth, logistic saturation, bifurcations, network cascades, feedback loops, conservation laws, diffusion processes, optimization under constraints, and so on.

We ended up with **84 distinct structure types**, each with a formal definition and multiple examples drawn from different domains.

### Generating Training Data

For each structure type, we wrote natural-language descriptions of real-world phenomena that exhibit that structure. The descriptions are deliberately written in everyday language, not equations -- because the model needs to learn that "the force drops off as you move away" and "the signal weakens with distance" and "influence fades with social distance" all share an inverse-square (or inverse-power) skeleton.

This produced **1,214 training descriptions** across dozens of scientific domains, from physics and chemistry to economics, ecology, urban planning, linguistics, and psychology.

### Fine-Tuning the Embedding Model

We fine-tuned a 110M-parameter Chinese text embedding model (based on `shibing624/text2vec-base-chinese`) using contrastive learning. Positive pairs: descriptions of different phenomena sharing the same structure type. Negative pairs: descriptions from different structure types.

The training objective is straightforward: push structurally identical descriptions together in embedding space, push structurally different ones apart.

### Evaluation

The results exceeded our expectations:

| Metric | Base Model | Fine-Tuned | 
|--------|-----------|------------|
| Silhouette Score | -0.01 | **0.85** |
| Retrieval@5 | 20.3% | **100%** |
| Retrieval@10 | 18.0% | **100%** |
| Intra-class similarity | 0.64 | **0.93** |
| Inter-class similarity | 0.57 | **0.17** |

The base model's silhouette score of -0.01 means its embeddings have essentially no structural clustering -- phenomena are grouped by topic, not by mathematical form. After fine-tuning, the silhouette score jumps to 0.85, indicating near-perfect structural clustering. Retrieval@5 going from 20% to 100% means that for any phenomenon, the 5 nearest neighbors in embedding space are *all* structurally isomorphic -- drawn from completely different domains but sharing the same mathematical skeleton.

## The Discovery Pipeline

With a working structural embedding, we built a discovery pipeline:

1. **Knowledge base**: 500 scientific phenomena, each described in natural language, spanning 87 domains.
2. **Pairwise comparison**: Encode all 500 phenomena, compute cosine similarity for all 124,251 pairs, filter for cross-domain, cross-structure-type matches above a similarity threshold.
3. **AI screening**: Multi-stage filtering using large language models to assess novelty, mechanistic depth, and testability.
4. **Equation verification**: For top candidates, explicitly map the equations from domain A to domain B and check whether the isomorphism holds at the formal level.

The funnel:
- **3,017** high-similarity cross-domain pairs
- **684** passed AI screening
- **72** rated A-grade (high novelty, high mechanistic depth)
- **6** survived full equation-level verification

## Three Discoveries That Surprised Us

### 1. Preisach Hysteresis Maps onto Ecological Regime Shifts

Magnetic materials exhibit hysteresis: when you magnetize a piece of iron and then reduce the field, it doesn't demagnetize along the same path. The Preisach model (1935) explains this using a distribution of micro-switches (hysterons) with different activation and deactivation thresholds.

Our engine matched this to ecological regime shifts -- the phenomenon where a lake that has become eutrophic (green, algae-dominated) doesn't clear up when you reduce phosphorus to the level at which it originally collapsed. The recovery threshold is different from the collapse threshold.

The structural mapping is precise: external magnetic field H maps to nutrient concentration, magnetization M maps to ecological state (water clarity), and the Preisach density function maps to the heterogeneity of species response thresholds.

**Why it matters**: Scheffer et al. (2001, 2009) established the theory of ecological regime shifts, but their framework lacks a tool for predicting exact recovery thresholds. The Preisach model, mature in physics for 90 years, could provide one. No published work has attempted this transfer.

### 2. Urban Innovation Follows an Arrhenius Equation

The Arrhenius equation describes how chemical reaction rates depend on temperature: k = A * exp(-Ea/RT). Higher temperature means molecules move faster, collide more often, and more collisions exceed the activation energy barrier.

Our model matched this to urban innovation scaling. Current theory (Bettencourt et al., 2007) describes innovation output as a power law of city size: I ~ N^beta with beta > 1. But this is purely descriptive -- it doesn't separate *why* bigger cities innovate more.

The Arrhenius mapping decomposes it: population density = collision frequency (how often people meet), cultural openness = temperature (how energetic the interactions are), and institutional barriers = activation energy (how hard it is to turn an encounter into a collaboration).

**Why it matters**: The power-law model has one parameter. The Arrhenius model has two independent policy levers. It predicts that lowering barriers to collaboration (reducing activation energy) is exponentially more effective than increasing population -- a testable and policy-relevant claim.

### 3. DeFi Liquidation Cascades as Elastic Collisions

When a DeFi position gets liquidated, collateral is seized and sold, crashing the price of the collateral asset, which triggers further liquidations. This cascade has been studied as a financial contagion problem.

Our engine matched it to elastic collisions in Newtonian mechanics. The mapping: collateral value = mass, asset price = velocity, liquidation event = collision. The conservation of momentum and energy in elastic collisions maps onto the conservation of total value and the redistribution of risk in liquidation cascades.

**Why it matters**: Elastic collision theory provides closed-form solutions for two-body interactions and well-developed perturbative methods for many-body problems. Importing this toolkit could give DeFi risk models analytical tractability that current simulation-based approaches lack.

## What We Learned

The most surprising finding isn't any individual discovery -- it's that the approach works at all. A small model (110M parameters), trained on just 1,214 examples, learns to see through natural language to mathematical structure well enough to find genuinely novel cross-domain connections that human researchers have missed.

This suggests that the space of unexplored structural isomorphisms is vast. The 72 A-grade discoveries we found are likely a small fraction of what exists. Many of them correspond to research programs that could take years to pursue.

We also learned the limits. The model works well for structures that can be described in a few sentences, but struggles with highly abstract or compositional structures (e.g., "a bifurcation of a network cascade"). The Chinese-language training data means it performs best on phenomena described in Chinese, though structural similarity is largely language-independent.

## Open Source

Everything is available:

- **Model weights**: The fine-tuned structural embedding model
- **Taxonomy**: All 84 structure types with definitions and examples
- **Training data**: 1,214 annotated descriptions
- **Knowledge base**: 500 phenomena across 87 domains
- **Discovery results**: All 684 screened discoveries with scores and analysis
- **Pipeline code**: End-to-end reproduction scripts

GitHub: [link]
Paper: [link]
Interactive explorer: [link]

## What's Next

Three directions we're excited about:

1. **Scaling the knowledge base**: 500 phenomena is a proof of concept. We want to reach 50,000, covering every quantitative field. The discovery count should scale super-linearly with the knowledge base size (more nodes = disproportionately more edges).

2. **Multilingual and multimodal**: Extending beyond Chinese, and incorporating equation images and diagrams alongside text descriptions.

3. **Validation at scale**: The 72 A-grade discoveries are hypotheses. We want to collaborate with domain experts to test them. If even a handful hold up under rigorous analysis, the approach will have proven its value as a tool for accelerating cross-disciplinary science.

The dream is a search engine where you describe a phenomenon in your field and it returns structurally isomorphic phenomena from fields you've never heard of -- complete with the equation mapping and a suggested research program.

We're not there yet. But the first 6 verified discoveries suggest we're on the right track.

---

*If you work on complex systems, analogical reasoning, embedding models, or any of the specific domains mentioned above, we'd love to hear from you. The most valuable feedback will come from domain experts who can tell us whether these structural mappings are trivially obvious, already known, or genuinely new.*
