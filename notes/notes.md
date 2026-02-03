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
* **Semantic Enrichment**: How do we turn the summary into a human-readable summary.
* **Personalization**: 
    * What do we define as a user interest?
    * Explain different modes


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
