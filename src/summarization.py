import json
from enum import Enum
from db_utils import *
from spark_utils import *


class Mode(Enum):
    STRICT = 1
    LOOSE = 2
    ASSOCIATION = 3


class SummarizationManager:
    def __init__(self, spark):
        self.spark = spark
        self.dataset = None
        self.node_count = None
        self.subgraph = None
        self.id_mappings = None
        self.association_rules = None
        self.node_labels = None
        self.default_properties = None

    def load(self, dataset):
        self.dataset = dataset
        self.node_count = self.__set_node_count()
        self.node_labels, self.default_properties = self.__set_node_properties()

    def to_node_list(self):
        return [int(i) for i in list(self.id_mappings.keys())]

    def set_subgraph(self, subgraph): self.subgraph = subgraph
    def set_id_mappings(self, id_mappings): self.id_mappings = id_mappings
    def set_association_rules(self, association_rules): self.association_rules = association_rules

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
            default_properties[x] = self.__find_default_property(label=x)

        return node_labels, default_properties
    
    def __set_node_count(self):
        return execute_query(self.spark, "MATCH (n) RETURN count(n) AS node_count").collect()[0]["node_count"]


def property_id_to_name(sm: SummarizationManager, node_list):
    # Build a dynamic Cypher CASE statement based on your dictionary
    # output example: WHEN 'Character' IN labels(n) THEN n.name
    case_statements = []
    for label, prop in sm.default_properties.items():
        case_statements.append(f"WHEN '{label}' IN labels(n) THEN n.{prop}")
    
    query = f"""
    MATCH (n)
    WHERE id(n) IN {node_list}
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
        WHERE id(n) IN {sm.to_node_list()}
            AND id(m) IN {sm.to_node_list()}
        RETURN
            [node IN nodes(p) | head(labels(node)) + ':' + {node_display_logic}] as path_nodes,
            [rel IN relationships(p) | type(rel)] as relationships
    """
    subgraph_df = execute_query(sm.spark, cypher_query)
    subgraph_df.show(truncate=False)

    # TODO: output the subgraph in a way maybe that neo4j understands it so we can do queries in the subgraph for personalization

    return subgraph_df, f"MATCH p = (n)-[*1..2]-(m)\nWHERE id(n) IN {sm.to_node_list()}\nAND id(m) IN {sm.to_node_list()}\nRETURN p"


def get_verbalization(sm: SummarizationManager):
    from google import genai

    client = genai.Client()

    # Format Rules: Convert to a nice string (e.g., Markdown or JSON)
    rules_text = ""
    # Get top 50 rules by confidence or lift
    rows = sm.association_rules.sort(col("lift").desc()).limit(50).collect()
    for row in rows:
        antec = [str(id) for id in row.antecedent]
        conseq = [str(id) for id in row.consequent]
        rules_text += f"{antec} --> {conseq}, {row.confidence}, {row.lift}, {row.support}\n"


    # Format Subgraph: Extract nodes/relationships
    # Assuming subgraph has 'p' (paths) or distinct nodes/rels
    # It's safer to just describe the nodes found in the subgraph
    # (Converting a whole graph to text is heavy, so we summarize)
    elements = sm.subgraph.limit(50).collect()
    subgraph_text = str([str(row) for row in elements])

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=f"""
            You are an AI system tasked with verbalizing data mining results.
            You are given:
            
            1) ASSOCIATION RULES extracted from transaction data.
            These rules represent STATISTICAL relationship and are in this format:
            [antecedent] --> [consequent], confidence, lift, support
            Association Rules:
            {rules_text}
            
            2) PROPERTIES OF ASSOCIATION RULES are mapped based on the IDs and
            consist of all the properties of the nodes in the ASSOCIATION RULES.
            They also include the "default_property" which is the property by which we can
            differentiate each node, other than the ID.
            {sm.id_mappings}

            3) A SUPPORTING SUBGRAPH extracted from a Property Graph.
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
            - Do not use the IDs in your answer just the properties and default properties.

            OUTPUT:
            A short explanatory text suitable for inclusion in a technical report.
        """
    )

    return response.text


def load_user_interests():
    data = {}
    with open('./data/user.json', 'r') as file:
        data = json.load(file)
    return data


# node_list is only used for Mode.ASSOCIATION
def filter_graph_based_on_user(sm: SummarizationManager, interests, mode:Mode=Mode.LOOSE):
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

    return_statement = f"""
    [node IN nodes(p) | head(labels(node)) + ':' + {node_display_logic}] as path_nodes,
    [rel IN relationships(p) | type(rel)] as relationships
    """

    if mode in [Mode.STRICT, Mode.LOOSE]:
        query = f"""
            MATCH p = (n)-[*..{mode.value}]-()
            WHERE {where_clause}
            RETURN
        """
    elif mode == Mode.ASSOCIATION:
        association(sm)

        # TODO: choose whether to connect between (interested,associated nodes) and (interested, associated nodes) 
        # or just between (interested nodes) and (interested, associated nodes)
        query = f"""
            MATCH (n)
            WHERE {where_clause}
            OR id(n) IN {sm.to_node_list()}
            WITH n
            MATCH p = (n)-[*..2]-(m)
            WHERE {where_clause.replace('n:', 'm:').replace('n.', 'm.')}
            OR id(m) IN {sm.to_node_list()}
            RETURN
        """

    print(query + return_statement)
    df = execute_query(sm.spark, query + return_statement)
    df.show(truncate=False)

    sm.set_subgraph(df)
    
    return query + " p"


def association(sm: SummarizationManager):
    # MAYBE: add WHERE id(s) < id(t) to avoid having both [A, B] and [B, A]
    # Create buckets for FPGrowth
    cypher_query = """
        MATCH (s)--(t)
        WITH s, collect(DISTINCT toString(id(t))) AS neighbors
        WHERE size(neighbors) > 1 AND size(neighbors) < 10
        RETURN neighbors + toString(id(s)) AS items
    """
    
    df = execute_query(sm.spark, cypher_query)
    
    # Optional: Cache the DF because FPGrowth reads it multiple times
    df.cache()
    
    minS, minC = find_minSupport_and_minConfidence(df, sm.node_count)
    fp = FPGrowth(itemsCol="items", minSupport=minS, minConfidence=minC)
    model = fp.fit(df)

    print("Frequent itemsets (Sorted by least frequent):")
    model.freqItemsets.sort("freq").show(100)
    model.associationRules.show(truncate=False)

    node_list = get_node_list(model.associationRules)
    id_mappings = property_id_to_name(sm, node_list)
    sm.set_id_mappings(id_mappings)


    # 
    cypher_query = f"""
        MATCH (n)
        WHERE id(n) IN {node_list}
        RETURN 
            id(n) AS node_id,
            properties(n) AS all_props
    """
    nodes_df = execute_query(sm.spark, cypher_query)
    # Collect to driver as a list of Rows
    rows = nodes_df.collect()

    final_output = {}

    for row in rows:
        n_id = row['node_id']
        raw_props = row['all_props']
        
        # Filter out "Unknown" values from the properties dictionary
        clean_props = {k: v for k, v in raw_props.items() if str(v).lower() != 'unknown'}
        
        # Construct the nested structure
        final_output[n_id] = {
            "default_property": id_mappings.get(n_id, "Unknown"),
            "properties": clean_props
        }

    sm.set_id_mappings(final_output)
    sm.set_association_rules(model.associationRules)


def general_summarization(sm: SummarizationManager):
    association(sm)

    subgraph, query = get_supporting_subgraph(sm)
    sm.set_subgraph(subgraph)

    return query