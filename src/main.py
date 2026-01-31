from dotenv import load_dotenv
from pyspark.ml.fpm import FPGrowth
from pyspark.sql.functions import col, explode

from db_utils import *
from spark_utils import *

spark = None
node_labels=[]
DATASET="star-wars"
default_properties={}


def get_node_list(df):
    df_ant = df.select(explode(col("`antecedent`")).alias("node"))
    df_con = df.select(explode(col("`consequent`")).alias("node"))

    distinct_nodes_df = df_ant.union(df_con).distinct()
    return list([int(row.node) for row in distinct_nodes_df.collect()])

def property_id_to_name(node_list):
    # Build a dynamic Cypher CASE statement based on your dictionary
    # output example: WHEN 'Character' IN labels(n) THEN n.name
    case_statements = []
    for label, prop in default_properties.items():
        case_statements.append(f"WHEN '{label}' IN labels(n) THEN n.{prop}")
    
    query = f"""
    MATCH (n)
    WHERE id(n) IN {node_list}
    RETURN id(n) as id,
           CASE {' '.join(case_statements)} ELSE 'Unknown' END as display_name
    """

    result = execute_query(spark, query)
    return {row["id"]: row["display_name"] for row in result.collect()}


def get_supporting_subgraph(node_list, limit=10):
    # 2. BUILD THE DYNAMIC CYPHER STRING
    # We build a CASE statement: CASE WHEN 'Character' IN labels(node) THEN node.name ...
    case_parts = []
    for label, prop in default_properties.items():
        # We use coalesce here just in case the expected property is missing on a specific node
        case_parts.append(f"WHEN '{label}' IN labels(node) THEN coalesce(node.{prop}, 'Unknown')")
    
    # Build the ELSE clause (The Fallback)
    # This creates: coalesce(node.name, node.title, node.label, ..., "Unknown")
    fallback_props = [f"node.{p}" for p in node_labels]
    else_part = f"ELSE coalesce({', '.join(fallback_props)}, toString(id(node)))" # Final fallback to internal ID
    
    # Combine into one string
    node_display_logic = f"CASE {' '.join(case_parts)} {else_part} END"

    # MAYBE: use allShortestPaths
    # 3. INSERT INTO QUERY
    cypher_query = f"""
        MATCH p = (n)-[*1..2]-(m)
        WHERE id(n) IN {node_list} 
            AND id(m) IN {node_list}
        RETURN 
            [node IN nodes(p) | {node_display_logic}] as path_nodes,
            [rel IN relationships(p) | type(rel)] as relationships
    """
    subgraph_df = execute_query(spark, cypher_query)
    subgraph_df.show(truncate=False)

    # TODO: output the subgraph in a way maybe that neo4j understands it so we can do queries in the subgraph for personalization

    return subgraph_df


def get_verbalization(subgraph, association_rules, id_mapping):
    from google import genai

    # TODO: Map IDs back to names/labels/titles
    client = genai.Client()

    # 1. PREPARE THE DATA
    # Spark DataFrames are lazy. We must .collect() data to Python to send it to the API.
    # We use .limit(50) to ensure we don't blow up the prompt token limit.
    

    # Format Rules: Convert to a nice string (e.g., Markdown or JSON)
    rules_text = ""
    # Get top 50 rules by confidence or lift
    rows = association_rules.sort(col("lift").desc()).limit(50).collect()
    for row in rows:
        antec = [str(id_mapping[int(id)]) for id in row.antecedent]
        conseq = [str(id_mapping[int(id)]) for id in row.consequent]
        rules_text += f"{antec} --> {conseq}, {row.confidence}, {row.lift}, {row.support}\n"


    # Format Subgraph: Extract nodes/relationships
    # Assuming subgraph has 'p' (paths) or distinct nodes/rels
    # It's safer to just describe the nodes found in the subgraph
    # (Converting a whole graph to text is heavy, so we summarize)
    elements = subgraph.limit(50).collect()
    subgraph_text = str([str(row) for row in elements])

    print("---------------------------------------------")
    print(f"RULES_TEXT: \n{rules_text}")
    print("---------------------------------------------")
    print(f"SUBGRAPH_TEXT: \n{subgraph_text}")
    print("---------------------------------------------")

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=f"""Based on these association rules: {rules_text} and this
                produced subgraph: {subgraph_text}, can you do a simple analysis of the results ?
                Please stick to the data provided to you and do not give general examples.
            """
    )

    with open("output/verbalization.md", "a") as f:
      f.write(f"\n\n---------------------------------\n{response.text}")

    print("Finished verbalization")


def find_minSupport_and_minConfidence(itemsets, node_count):
    currMinSupport = 0.1
    currMinConfidence = 0.5

    for _ in range(10):
        fp = FPGrowth(itemsCol="items", minSupport=currMinSupport, minConfidence=currMinConfidence)
        model = fp.fit(itemsets)
        node_list = get_node_list(model.associationRules)

        # check if association rules consist at least 2% of all the nodes
        if(len(node_list) >= 0.02 * node_count): break

        currMinSupport = currMinSupport / 1.5
        # MAYBE: do not decrease confidence, or do by very little every second iteration
        # currMinConfidence = currMinConfidence / 1.5

    print(f"MIN_SUPPORT: {currMinSupport}")
    print(f"MIN_CONFIDENCE: {currMinConfidence}")
    return currMinSupport, currMinConfidence


def main():
    global spark, node_labels, default_properties

    load_dotenv()

    spark = init_spark()
    node_labels, default_properties = get_node_properties(DATASET)

    node_count = execute_query(spark, "MATCH (n) RETURN count(n) AS node_count").collect()[0]["node_count"]




    # MAYBE: add WHERE id(s) < id(t) to avoid having both [A, B] and [B, A]
    cypher_query = """
        MATCH (s)--(t)
        WITH s, collect(DISTINCT toString(id(t))) AS neighbors
        WHERE size(neighbors) > 1 AND size(neighbors) < 10
        RETURN neighbors + toString(id(s)) AS items
    """
    
    df = execute_query(spark, cypher_query)
    
    # Optional: Cache the DF because FPGrowth reads it multiple times
    df.cache()
    
    minS, minC = find_minSupport_and_minConfidence(df, node_count)
    fp = FPGrowth(itemsCol="items", minSupport=minS, minConfidence=minC)
    model = fp.fit(df)

    print("Frequent itemsets (Sorted by least frequent):")
    model.freqItemsets.sort("freq").show(100)
    model.associationRules.show(truncate=False)

    node_list = get_node_list(model.associationRules)
    subgraph = get_supporting_subgraph(node_list)
    id_mappings = property_id_to_name(node_list)
    print(id_mappings)
    # UNCOMMENT:
    get_verbalization(subgraph, model.associationRules, id_mappings)

    spark.stop()

if __name__ == "__main__":
    main()