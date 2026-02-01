import json
from enum import Enum
from pyspark.ml.fpm import FPGrowth
from pyspark.sql.functions import col, explode

from db_utils import *
from spark_utils import *

# spark = None
# node_labels=[]
# node_count = 0
# DATASET="star-wars"
# default_properties={}

class Mode(Enum):
    STRICT = 1
    LOOSE = 2
    ASSOCIATION = 3


class SummarizationManager:
    def __init__(self, spark):
        self.spark = spark
        self.dataset = None
        self.node_list = None        
        self.node_labels = None
        self.default_properties = None

    def load(self, dataset):
        self.dataset = dataset
        self.node_labels, self.default_properties = self.__set_node_properties()

    def set_node_list(self, node_list): self.node_list = node_list

    def __find_default_property(self, label):
        property_list = ["name","title","label","id","uid","username","code"]

        with open(f'./data/datasets/{self.dataset}/{self.dataset}_node_types.csv') as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            for row in csv_reader:
                if row[0] == label:
                    clean_list = [item.strip() for item in row[1].replace("[", "").replace("]", "").split(",")]
                    for property in property_list:
                        if property in clean_list: return property

                    # TODO: Maybe select at random, for now just return the first property
                    return clean_list[0]

            print(f"Label '{label}' is not part of the PG")
            return None

    def __set_node_properties(self):
        node_labels = []
        default_properties = {}

        # Find node labels and their default property
        with open(f'./data/datasets/{self.dataset}/node_labels.csv') as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            for row in csv_reader:
                if str(row[0]) == "label": continue
                node_labels.append(str(row[0]))
        
        for x in node_labels:
            default_properties[x] = find_default_property(self.dataset, label=x)

        return node_labels, default_properties


def get_node_list(df):
    df_ant = df.select(explode(col("`antecedent`")).alias("node"))
    df_con = df.select(explode(col("`consequent`")).alias("node"))

    distinct_nodes_df = df_ant.union(df_con).distinct()
    return list([int(row.node) for row in distinct_nodes_df.collect()])


def property_id_to_name(sm: SummarizationManager):
    # Build a dynamic Cypher CASE statement based on your dictionary
    # output example: WHEN 'Character' IN labels(n) THEN n.name
    case_statements = []
    for label, prop in sm.default_properties.items():
        case_statements.append(f"WHEN '{label}' IN labels(n) THEN n.{prop}")
    
    query = f"""
    MATCH (n)
    WHERE id(n) IN {sm.node_list}
    RETURN id(n) as id,
           CASE {' '.join(case_statements)} ELSE 'Unknown' END as display_name
    """

    result = execute_query(sm.spark, query)
    return {row["id"]: row["display_name"] for row in result.collect()}


def get_supporting_subgraph(sm: SummarizationManager, limit=10):
    # 2. BUILD THE DYNAMIC CYPHER STRING
    # We build a CASE statement: CASE WHEN 'Character' IN labels(node) THEN node.name ...
    case_parts = []
    for label, prop in sm.default_properties.items():
        # We use coalesce here just in case the expected property is missing on a specific node
        case_parts.append(f"WHEN '{label}' IN labels(node) THEN coalesce(node.{prop}, 'Unknown')")
    
    # Build the ELSE clause (The Fallback)
    # This creates: coalesce(node.name, node.title, node.label, ..., "Unknown")
    fallback_props = [f"node.{p}" for p in sm.node_labels]
    else_part = f"ELSE coalesce({', '.join(fallback_props)}, toString(id(node)))" # Final fallback to internal ID
    
    # Combine into one string
    node_display_logic = f"CASE {' '.join(case_parts)} {else_part} END"

    # MAYBE: use allShortestPaths
    # 3. INSERT INTO QUERY
    cypher_query = f"""
        MATCH p = (n)-[*1..2]-(m)
        WHERE id(n) IN {sm.node_list} 
            AND id(m) IN {sm.node_list}
        RETURN 
            [node IN nodes(p) | {node_display_logic}] as path_nodes,
            [rel IN relationships(p) | type(rel)] as relationships
    """
    subgraph_df = execute_query(sm.spark, cypher_query)
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
        contents=f"""
            You are an AI system tasked with verbalizing data mining results.
            You are given:
            
            1) ASSOCIATION RULES extracted from transaction data.
            These rules represent STATISTICAL relationship and are in this format:
            [antecedent] --> [consequent], condifence, lift, support
            Association Rules:
            {rules_text}
            
            2) A SUPPORTING SUBGRAPH extracted from a Property Graph.
            The subgraph provides STRUCTURAL and SEMANTIC context only.
            It does NOT encode frequency, confidence, or support values.
            Supporting Subgraph:
            {subgraph_text}
            
            TASK:
            Write a concise verbalization that:
            - Clearly states the statistical association described by the rules.
            - Uses the subgraph ONLY as contextual or semantic evidence.
            - Explains *why the association is plausible* based on graph structure.
            - Does NOT claim that the subgraph explains numerical values.
            - Does NOT introduce entities or relationships not present in the data.
            - Describe the relationship between the nodes of the graph and how strong they are.

            STYLE GUIDELINES:
            - Be precise and factual.
            - Avoid generic explanations or examples.
            - Do not speculate beyond the provided data.
            - Write in clear, academic-style English (2-4 paragraphs max).

            OUTPUT:
            A short explanatory text suitable for inclusion in a technical report.
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


def load_user_interests():
    data = {}
    with open('./data/user.json', 'r') as file:
        data = json.load(file)
    return data


# node_list is only used for Mode.ASSOCIATION
def filter_graph_based_on_user(sm: SummarizationManager, mode:Mode=Mode.LOOSE):
    interests = load_user_interests()

    query = ""
    conditions = []
    for label, names in interests.items():
        # Determine if we should look for 'name' or 'title' 
        # (You can use your default_properties dict here)
        prop = sm.default_properties[label]
        
        # Format the list for Cypher: ["A", "B"]
        formatted_names = str(names)
        conditions.append(f"(n:{label} AND n.{prop} IN {formatted_names})")

    where_clause = "\nOR ".join(conditions)

    if mode in [Mode.STRICT, Mode.LOOSE]:
        query = f"""
            MATCH p = (n)-[*..{mode.value}]-()
            WHERE {where_clause}
            RETURN p
        """
    elif mode == Mode.ASSOCIATION:
        # TODO: choose whether to connect between (interested,associated nodes) and (interested, associated nodes) 
        # or just between (interested nodes) and (interested, associated nodes)
        query = f"""
            MATCH (n)
            WHERE {where_clause}
            OR id(n) IN {sm.node_list}
            WITH n
            MATCH p = (n)-[*..2]-(m)
            WHERE {where_clause.replace('n:', 'm:').replace('n.', 'm.')}
            OR id(m) IN {sm.node_list}
            RETURN p
        """

    print(query)
    df = execute_query(sm.spark, query)
    df.show(truncate=False)


def general_summarization(sm: SummarizationManager, node_count):
    # MAYBE: add WHERE id(s) < id(t) to avoid having both [A, B] and [B, A]
    cypher_query = """
        MATCH (s)--(t)
        WITH s, collect(DISTINCT toString(id(t))) AS neighbors
        WHERE size(neighbors) > 1 AND size(neighbors) < 10
        RETURN neighbors + toString(id(s)) AS items
    """
    
    df = execute_query(sm.spark, cypher_query)
    
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

    return node_list, id_mappings, subgraph


# def init():
#     node_labels, default_properties = get_node_properties(DATASET)
#     node_count = execute_query(spark, "MATCH (n) RETURN count(n) AS node_count").collect()[0]["node_count"]

#     # UNCOMMENT:
#     # get_verbalization(subgraph, model.associationRules, id_mappings)
#     # filter_graph_based_on_user(node_list)
#     # filter_graph_based_on_user(node_list, Mode.STRICT)
#     # filter_graph_based_on_user(node_list, Mode.ASSOCIATION)
#     # spark.stop()
    
#     return spark, node_labels, default_properties, node_count


# if __name__ == "__main__":
#     main()