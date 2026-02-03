### NOTHING :) 🙃 ###

init_object  --> spark 
dataset --> load_dataset --> node_labels, default_properties, node_count


GENERAL SUMMARY:
association --> id_mappings, association_rules
id_mappings, association_rules           --> general_summarization --> subgraph
id_mappings, association_rules, subgraph --> verbalization         --> verbalization_text

PERSONALIZED SUMMARY:
interests, mode --> personalized_summary --> subgraph
id_mappings, association_rulesm subgraph --> verbalization --> verbalization_text


 


# Presentation 


* the problem? what is ARM, what is PGs etc., general info/knowledge

### Methodology
* **Graph Extraction**: How you traverse the Property Graph to create "transactions" (since ARM usually requires transactional data).
* **Rule Mining**: 
    * Algorithm used (e.g., Apriori or FP-Growth) 
    * How you define Support and Confidence in a graph context
* **Semantic Summary Generation**: How do we turn the summary into a human-readable summary.
    * subgraph
    * LLM -> human readable
* **Personalization**: 
    * What do we define as a user interest?
    * Explain different modes
        * input/output


### Key Metrics & Logic
Explain the "Association Rules" specifically for Property Graphs.\
Use a table to show what the data looks like:
| Concept | Definition in your Project |
| - | - |
| Antecedent | The "If" part (e.g., a node has Property A and Label B). | 
| Consequent | The "Then" part (e.g., it is $80\%$ likely to have an edge to Node C). | 
| Support | How often this pattern appears across the whole graph. | 
| Confidence | How reliable the rule is when the antecedent is present. | 
| Lift | ??? | 


#### Specific to our implementation (Testbed?)
* **Datasets** 
    * Mention the datasets used (`Neo4j`)
* **Results** 
    * Between different datasets - execution time
    * Comparison betweeen general/personalized


---



This transformation is considered valid because it leverages the **Structural Locality** of a graph to satisfy the "Transaction" requirement of frequent itemset mining (like FPGrowth).

In traditional data mining, a transaction is a set of items that occur together (like products in a shopping cart). In a property graph, there is no inherent "shopping cart," so we must define what constitutes a set of related items based on the graph's topology.

### Why it is a valid transformation:

* **Neighborhood as Context**: The transformation assumes that a node () and its immediate neighbors () form a coherent semantic unit. This follows the "homophily" principle—entities connected in a graph likely share a meaningful relationship or context.
* **Itemset Generation**: By collecting the IDs of neighbors and the source node into a single list, you create a "Basket" of entities. The algorithm can then count how often certain groups of IDs appear together across many different neighborhoods.
* **Statistical Relevance**:
* **The Lower Bound (`> 1`)**: Validates the transformation by ensuring only "interactions" are studied. A node with zero or one neighbor cannot form an "association" with other items, making it noise in a transaction database.
* **The Upper Bound (`< 10`)**: Prevents "Super-node Bias". If a node is connected to everything (like a very common Category label), it would appear in almost every transaction, leading to "rules" that are mathematically strong but semantically useless.


* **Identity Inclusion**: Including `id(s)` in the list `neighbors + toString(id(s))` ensures the transaction represents a full ego-network. This allows the algorithm to find rules like `[Neighbor_A] --> [Source_Node]`, identifying which neighbors are strongest predictors of a specific entity's presence.

### Summary of the Logic

This transformation effectively maps a **Discrete Graph Structure** into a **Transactional Database**. It is valid because it preserves the local connectivity of the graph while providing the specific data shape (a list of items) required by the FPGrowth algorithm to calculate support, confidence, and lift.

Would you like me to show you how to filter this query further so that only specific types of nodes (e.g., only "Films" or "Actors") are used as the "items" in your transactions?


---

Here is a breakdown of the function’s logic, formatted as clear, high-level bullet points suitable for a presentation slide:

## Dynamic Parameter Tuning for FP-Growth

* **Initial Thresholds**: Sets a starting point with a Minimum Support of **10%** and Minimum Confidence of **50%**.
* **Iterative Optimization**: Runs a loop for up to **10 iterations** to find the "sweet spot" for rule generation.
* **Rule Mining**: Executes the **FP-Growth algorithm** on the dataset using the current thresholds in each cycle.
* **Sparsity Check**: Evaluates the results by checking if the generated association rules cover at least **2% of the total node count**.
* **Adaptive Decay**: If the 2% threshold isn't met, it aggressively **reduces Minimum Support (divided by 1.5)** to capture more frequent itemsets.
* **Stability Control**: Keeps Minimum Confidence constant (noted as a potential area for minor adjustment) to maintain the quality of the rules.
* **Auto-Termination**: Breaks the loop early once sufficient node coverage is achieved and outputs the optimized parameters.

---

> **Key Takeaway:** This function automates the "trial and error" process of setting hyperparameters, ensuring the model isn't too restrictive to produce meaningful data.

Would you like me to create a quick visual flowchart of this loop to include in your slides?


---
This approach is valid because it addresses one of the most common challenges in data mining: **The Cold Start Problem.**

In many datasets, you don't know the density of transactions beforehand. If your `minSupport` is too high, the algorithm returns zero results; if it’s too low, it crashes your memory with millions of useless rules.

Here is why this iterative approach is a sound engineering choice:

### 1. Heuristic-Based Scaling

Instead of guessing a support value, the function uses an **exponential decay** (). This allows the algorithm to quickly "scan" through higher thresholds and only dive into computationally expensive lower thresholds if necessary.

### 2. Statistical Representation

The "Validity" check here is the **2% node coverage** rule.

* It ensures the model is **representative** of the global dataset.
* By linking the stop-condition to `node_count`, the function adapts to the scale of your specific graph or database.

### 3. Maintaining Rule Quality

You’ll notice the code (currently) leaves `minConfidence` untouched at 0.5. This is a smart validity check:

* **Support** measures how *frequent* a pattern is.
* **Confidence** measures how *reliable* the rule is.
* By lowering support but keeping confidence steady, you are saying: "I'm willing to look at rarer items, but I still require the relationship between them to be strong."

---

### Comparison of Approaches

| Manual Tuning | This Iterative Function |
| --- | --- |
| Risk of empty sets or "Null" results. | Guaranteed to attempt to find a result. |
| Time-consuming "guess and check." | Automated and reproducible. |
| Hardcoded values fail on new data. | Dynamic; scales with `node_count`. |

---

**Next Step:** Would you like me to rewrite the code to include that "MAYBE" comment's logic—decreasing confidence slightly every few iterations to make the search even more robust?



---

# SUMMURIZATION GENERAL STAR_WARS
Summary
Based on the association rules, the data reveals strong statistical dependencies within the Star Wars film franchise, clearly clustering the films into their respective trilogies. The strongest correlations appear among the original trilogy films: A New Hope, The Empire Strikes Back, and Return of the Jedi. Most notably, the presence of A New Hope and The Empire Strikes Back in a transaction predicts the presence of Return of the Jedi with a confidence of 1.0 (100%) and a high lift of 4.47, suggesting these items are almost invariably linked. A secondary, distinct cluster involves the prequel trilogy, where The Phantom Menace and Attack of the Clones serve as antecedents for Revenge of the Sith with a confidence of 0.68 and a lift of 1.95.

The plausibility of these high-strength association rules is supported structurally by the provided property graph, which maps dense "APPEARED_IN" relationships between these films and a shared set of characters. The absolute confidence observed within the original trilogy corresponds to the graph's depiction of core protagonists—such as Luke Skywalker, Leia Organa, and Han Solo—appearing consistently across A New Hope, The Empire Strikes Back, and Return of the Jedi. Similarly, the inter-trilogy connections are contextualized by the graph nodes for characters like Obi-Wan Kenobi, Yoda, and Palpatine, who bridge the narrative gap between the prequels and the original films. Additionally, the rule associating the Human species with Attack of the Clones is structurally validated by the graph's numerous edges linking the Human node to specific characters appearing in that film.

#### star-wars personalized association

Based on the extracted association rules, the transaction data reveals distinct high-frequency co-occurrence patterns among films within the Star Wars saga. The strongest statistical relationships exist between A New Hope, The Empire Strikes Back, and Return of the Jedi. Notably, the combination of A New Hope and The Empire Strikes Back predicts the presence of Return of the Jedi with 100% confidence and a lift value exceeding 4.46, indicating a highly dependent relationship. This statistical grouping is structurally supported by the property graph, which links these titles through shared narrative nodes, specifically the character Darth Vader and the planet Tatooine, suggesting that shared entities drive the transactional affinity.

A secondary cluster of rules identifies a correlation between The Phantom Menace, Attack of the Clones, and Revenge of the Sith. While the association is slightly weaker than the previous group, it remains significant; for example, transactions containing The Phantom Menace and Attack of the Clones imply Revenge of the Sith with approximately 68% confidence and a lift near 1.95. The supporting subgraph provides semantic plausibility for this pattern by illustrating that the character Anakin Skywalker serves as a central hub connecting these three films, appearing as a pilot and key figure across this specific triad.

Finally, the data indicates a moderate association between the species Human and the film Attack of the Clones (Lift: ~1.55). The graph structure contextualizes this statistical link by explicitly defining relationships where central characters like Anakin Skywalker and Darth Vader are instances of the Human species. This suggests that the prevalence of human characters in the structural data mirrors the frequency of the species' appearance alongside specific film titles in the transaction logs.

# συγκεκριμεννη αλλα πιο ολοκληρωμενη

#### star-wars personalized strict

Based on the extracted association rules, the data reveals strong statistical dependencies clustered primarily around film trilogies within the Star Wars franchise. The strongest associations exist between A New Hope, The Empire Strikes Back, and Return of the Jedi. Specifically, the presence of both A New Hope and The Empire Strikes Back implies the presence of Return of the Jedi with absolute certainty (Confidence 1.0) and a high lift of approximately 4.47, indicating a relationship significantly stronger than random chance. The supporting subgraph provides semantic plausibility for this cluster through shared narrative elements; for example, the character Darth Vader is explicitly linked via "APPEARED_IN" relationships to all three of these films, acting as a central node that structurally binds the trilogy.

A distinct but slightly weaker set of rules governs the prequel films: The Phantom Menace, Attack of the Clones, and Revenge of the Sith. The combination of The Phantom Menace and Attack of the Clones predicts Revenge of the Sith with a confidence of approximately 0.68 and a lift of 1.95. While statistically significant, these metrics are lower than those observed in the original trilogy. This grouping is contextually supported by the property graph, which shows Anakin Skywalker as a distinct entity from Darth Vader, possessing "APPEARED_IN" relationships with all three prequel films, thereby establishing a narrative continuity that mirrors the statistical findings.

Finally, the rules highlight a specific association between the 'Human' species and the film Attack of the Clones (Confidence 0.53, Lift 1.55). This statistical correlation is structurally reinforced by the subgraph, which identifies key characters such as Anakin Skywalker and Darth Vader as belonging to the 'Human' species. The graph specifically links Anakin Skywalker to Attack of the Clones as a pilot and character, offering a semantic explanation for why the 'Human' property frequently co-occurs with this specific film in the transaction data.


#### star-wars personalized loose
Based on the extracted association rules, the data reveals a particularly robust statistical relationship between the films comprising the original Star Wars trilogy. The strongest observed rule indicates that the presence of A New Hope and The Empire Strikes Back predicts the inclusion of Return of the Jedi with a confidence of 1.0 and a lift value of approximately 4.47. Similarly, the combination of A New Hope and Return of the Jedi implies The Empire Strikes Back with high confidence (0.81) and lift (4.73). These metrics suggest that these three entities form a tightly knit cluster, appearing together frequently in the transaction data.

The plausibility of this high-strength association is supported by the structural context provided in the property graph. The subgraph illustrates that key narrative nodes, specifically the character Darth Vader, serve as bridges between A New Hope and The Empire Strikes Back. Vader is explicitly linked to consistent supporting entities across these films, including characters like Luke Skywalker and Leia Organa, and vehicles such as the TIE Advanced x1. This shared structural connectivity reflects a continuity of content that aligns with the statistical tendency for these films to co-occur.

A distinct but comparatively weaker grouping is evident among the prequel films. The combination of The Phantom Menace and Attack of the Clones predicts Revenge of the Sith with a confidence of roughly 0.68 and a lift of 1.95. While these values indicate a positive correlation (lift > 1), they are notably lower than those found in the original trilogy cluster. Additionally, the analysis identifies a specific association between the "Human" species and Attack of the Clones, suggesting a moderate dependency between this biological classification and the film, distinct from the film-to-film relationships.