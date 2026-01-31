import os
from dotenv import load_dotenv
from pyspark.ml.fpm import FPGrowth
from pyspark.sql.functions import col, explode

import db_utils
import spark_utils

spark = None

node_labels=[]
default_properties={}


def property_id_to_name(rules_df):
    df_ant = rules_df.select(explode(col("`antecedent`")).alias("node"))
    df_con = rules_df.select(explode(col("`consequent`")).alias("node"))

    distinct_nodes_df = df_ant.union(df_con).distinct()
    node_list = list([int(row.node) for row in distinct_nodes_df.collect()])
    print(f"NODE LIST: {node_list}")

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

    result = spark_utils.execute_query(spark, query)
    return {row["id"]: row["display_name"] for row in result.collect()}


def get_supporting_subgraph(rules_df, limit=10):
    df_ant = rules_df.select(explode(col("`antecedent`")).alias("node"))
    df_con = rules_df.select(explode(col("`consequent`")).alias("node"))

    distinct_nodes_df = df_ant.union(df_con).distinct()
    node_list = list([int(row.node) for row in distinct_nodes_df.collect()])
    print(f"NODE LIST: {node_list}")

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
    subgraph_df = spark_utils.execute_query(spark, cypher_query)
    subgraph_df.show(truncate=False)

    # TODO: output the subgraph in a way maybe that neo4j understands it so we can do queries in the subgraph for personalization

    return subgraph_df


def get_verbalization(subgraph=None, association_rules=None):
    import json
    from google import genai

    # TODO: Map IDs back to names/labels/titles
    client = genai.Client()

    # 1. PREPARE THE DATA
    # Spark DataFrames are lazy. We must .collect() data to Python to send it to the API.
    # We use .limit(50) to ensure we don't blow up the prompt token limit.
    
    # Format Rules: Convert to a nice string (e.g., Markdown or JSON)
    rules_data = []
    rules_text = ""
    if association_rules:
        # Get top 20 rules by confidence or lift
        rows = association_rules.sort(col("lift").desc()).limit(50).collect()
        for row in rows:
            rules_text += f"({row.antecedent}) --> ({row.consequent}), {row.confidence}, {row.lift}, {row.support}\n"
            # rules_data.append({
            #     "antecedent": row.antecedent,
            #     "consequent": row.consequent,
            #     "confidence": round(row.confidence, 3),
            #     "lift": round(row.lift, 3)
            # })s
    # rules_text = json.dumps(rules_data, indent=2)

    # Format Subgraph: Extract nodes/relationships
    subgraph_text = "No subgraph data provided."
    if subgraph:
        # Assuming subgraph has 'p' (paths) or distinct nodes/rels
        # It's safer to just describe the nodes found in the subgraph
        # (Converting a whole graph to text is heavy, so we summarize)
        elements = subgraph.limit(50).collect()
        subgraph_text = str([str(row) for row in elements])

    # (antecendts, ) --> (consq.. ) , confidence, lift

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

        df_ant = model.associationRules.select(explode(col("`antecedent`")).alias("node"))
        df_con = model.associationRules.select(explode(col("`consequent`")).alias("node"))

        distinct_nodes_df = df_ant.union(df_con).distinct()
        node_list = list([int(row.node) for row in distinct_nodes_df.collect()])

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
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

    spark = spark_utils.init_spark()
    node_labels, default_properties = db_utils.get_node_properties()

    # DELETE:
    cypher_query = """
        MATCH (n)-[r]-()
        RETURN id(n) AS node_id, count(r) AS freq
        ORDER BY freq DESC
    """
    df = spark_utils.execute_query(spark, cypher_query)
    df.show(20, truncate=False)
    print(f"ITEM COUNT: {df.distinct().count()}")
    node_count = df.distinct().count()

    # TODO: find a better way to get the count of all nodes (this is needed later)


    # MAYBE: add WHERE id(s) < id(t) to avoid having both [A, B] and [B, A]
    cypher_query = """
        MATCH (s)--(t)
        WITH s, collect(DISTINCT toString(id(t))) AS neighbors
        WHERE size(neighbors) > 1 AND size(neighbors) < 10
        RETURN neighbors + toString(id(s)) AS items
    """
    
    df = spark_utils.execute_query(spark, cypher_query)
    
    # Optional: Cache the DF because FPGrowth reads it multiple times
    df.cache()

    # DELETE:
    total_count = df.count()
    print(f"Total Transactions: {total_count}")
    
    minS, minC = find_minSupport_and_minConfidence(df, node_count)
    
    fp = FPGrowth(itemsCol="items", minSupport=minS, minConfidence=minC)
    model = fp.fit(df)

    print("Frequent itemsets (Sorted by least frequent):")
    # 3. Sorting by "freq" (default is ascending) shows the rare items first
    model.freqItemsets.sort("freq").show(100)
    # print("Association rules:")
    model.associationRules.show(truncate=False)

    subgraph = get_supporting_subgraph(model.associationRules)
    get_verbalization(subgraph, model.associationRules)

    id_mappings = property_id_to_name(model.associationRules)
    print(id_mappings)

    spark.stop()

if __name__ == "__main__":
    main()