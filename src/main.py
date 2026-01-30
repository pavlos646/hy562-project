import os
import csv
from dotenv import load_dotenv
from pyspark.ml.fpm import FPGrowth
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, explode

spark = None
neo4j_url = "bolt://[0:0:0:0:0:0:0:0]:7687"
neo4j_user = "neo4j"
neo4j_pass = "password"

node_labels=[]
default_properties={}
DATASET="star-wars"


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
    subgraph_df = execute_query(cypher_query)
    subgraph_df.show(truncate=False)

    # TODO: output the subgraph in a way maybe that neo4j understands it so we can do queries in the subgraph for personalization

    return subgraph_df


def execute_query(query):
    return spark.read \
        .format("org.neo4j.spark.DataSource") \
        .option("url", neo4j_url) \
        .option("authentication.type", "basic") \
        .option("authentication.basic.username", neo4j_user) \
        .option("authentication.basic.password", neo4j_pass) \
        .option("query", query) \
        .load()


def find_default_property(label):
    property_list = ["name","title","label","id","uid","username","code"]

    with open('./data/datasets/star-wars/star-wars_node_types.csv') as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            if row[0] == label:
                clean_list = [item.strip() for item in row[1].replace("[", "").replace("]", "").split(",")]
                for property in property_list:
                    if property in clean_list: return property

                # TODO: Maybe select at random, for now just return the first property
                return clean_list[0]

        print(f"ERROR: Label '{label}' is not part of the PG")
        return None


def filter_out_god_nodes(raw_baskets):
    basket = None
    # import pandas as pd
    from sklearn.feature_extraction.text import TfidfVectorizer
    # from mlxtend.preprocessing import TransactionEncoder
    # from mlxtend.frequent_patterns import fpgrowth

    # 1. Your raw baskets from the Neo4j query
    # raw_baskets = [
    #     ["Luke", "R2-D2", "X-Wing", "Tatooine"],
    #     ["Han", "R2-D2", "Falcon", "Tatooine"],
    #     ["Leia", "R2-D2", "Falcon", "Alderaan"],
    #     ["Luke", "Yoda", "X-Wing", "Dagobah"]
    # ]

    # 2. Convert baskets to "sentences" for TfidfVectorizer
    # We join names with underscores to keep "Darth Vader" as one token
    sentences = [" ".join([item.replace(" ", "_") for item in basket]) for basket in raw_baskets]

    raw_baskets.foreach(" ".join([item.replace(" ", "_") for item in basket]))

    # 3. Use max_df to automatically kill "God Nodes"
    # max_df=0.7 means "remove items that appear in more than 70% of baskets"
    tfidf = TfidfVectorizer(max_df=0.7, token_pattern=r"(?u)\b\w+\b")
    tfidf_matrix = tfidf.fit_transform(sentences)

    print("TF_IDF Matrix:")
    print(tfidf_matrix)

    # Get the list of "Meaningful" items (the ones that survived)
    survived_items = set(tfidf.get_feature_names_out())

    # 4. Rebuild the baskets using only survivors
    clean_baskets = [
        [item.replace(" ", "_") for item in basket if item.replace(" ", "_") in survived_items]
        for basket in raw_baskets
    ]

    for i in range(15):
        print(f"{i+1}: {clean_baskets[i]}")
    

    # MAYBE: 5. Run FP-Growth on the cleaned data
    # te = TransactionEncoder()
    # te_ary = te.fit(clean_baskets).transform(clean_baskets)
    # df = pd.DataFrame(te_ary, columns=te.columns_)

    # frequent_itemsets = fpgrowth(df, min_support=0.4, use_colnames=True)
    # print(frequent_itemsets)


    #----------------------
    from pyspark.ml.feature import HashingTF, IDF

    # 1. Calculate Term Frequency
    baskets_df = None
    hashingTF = HashingTF(inputCol="items", outputCol="rawFeatures")
    tf_df = hashingTF.transform(baskets_df)

    # 2. Calculate Inverse Document Frequency
    idf = IDF(inputCol="rawFeatures", outputCol="features")
    idfModel = idf.fit(tf_df)
    rescale_df = idfModel.transform(tf_df)


def get_verbalization(subgraph=None, association_rules=None):
    import json
    from google import genai

    # TODO: Map IPs back to names/labels/titles
    client = genai.Client()

    # 1. PREPARE THE DATA
    # Spark DataFrames are lazy. We must .collect() data to Python to send it to the API.
    # We use .limit(50) to ensure we don't blow up the prompt token limit.
    
    # Format Rules: Convert to a nice string (e.g., Markdown or JSON)
    rules_data = []
    if association_rules:
        # Get top 20 rules by confidence or lift
        rows = association_rules.sort(col("lift").desc()).limit(50).collect()
        for row in rows:
            rules_data.append({
                "antecedent": row.antecedent,
                "consequent": row.consequent,
                "confidence": round(row.confidence, 3),
                "lift": round(row.lift, 3)
            })
    rules_text = json.dumps(rules_data, indent=2)

    # Format Subgraph: Extract nodes/relationships
    subgraph_text = "No subgraph data provided."
    if subgraph:
        # Assuming subgraph has 'p' (paths) or distinct nodes/rels
        # It's safer to just describe the nodes found in the subgraph
        # (Converting a whole graph to text is heavy, so we summarize)
        elements = subgraph.limit(50).collect()
        subgraph_text = str([str(row) for row in elements])


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


def main():
    global spark, node_labels

    load_dotenv()
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

    spark = SparkSession.builder \
        .appName("HY562-Step2-Neo4j-To-Baskets") \
        .master("local[*]") \
        .config("spark.driver.memory", "8g") \
        .config("spark.jars.packages", "org.neo4j:neo4j-connector-apache-spark_2.13:5.4.0_for_spark_3") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")

    print(f"Connecting to {neo4j_url}...")

    # TODO: getting  the info dynamically.
    # df.show(20, truncate=False)

    # Find node labels and their default property
    with open(f'./data/datasets/{DATASET}/node_labels.csv') as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            if str(row[0]) == "label": continue
            node_labels.append(str(row[0]))
    
    for x in node_labels:
        default_properties[x] = find_default_property(x)
    
    cypher_query = """
    MATCH (n)-[r]-()
    RETURN id(n) AS node_id, count(r) AS freq
    ORDER BY freq DESC
    """
    df = execute_query(cypher_query)
    df.show(20, truncate=False)
    print(f"ITEM COUNT: {df.distinct().count()}")


    # MAYBE: add WHERE id(s) < id(t) to avoid having both [A, B] and [B, A]
    cypher_query = """
        MATCH (s)--(t)
        WITH s, collect(DISTINCT toString(id(t))) AS neighbors
        WHERE size(neighbors) > 1 AND size(neighbors) < 10
        RETURN neighbors + toString(id(s)) AS items
    """
    
    df = execute_query(cypher_query)
    
    # Optional: Cache the DF because FPGrowth reads it multiple times
    df.cache()

    # TODO: more dynamically find minsupport
    total_count = df.count()
    
    print(f"Total Transactions: {total_count}")
    fp = FPGrowth(itemsCol="items", minSupport=0.1, minConfidence=0.5)
    model = fp.fit(df)

    print("Frequent itemsets (Sorted by least frequent):")
    # 3. Sorting by "freq" (default is ascending) shows the rare items first
    model.freqItemsets.sort("freq").show(100)
    # print("Association rules:")
    model.associationRules.show(truncate=False)

    subgraph = get_supporting_subgraph(model.associationRules)
    get_verbalization(subgraph, model.associationRules)

    spark.stop()

if __name__ == "__main__":
    main()