import csv
from pyspark.ml.fpm import FPGrowth
from pyspark.sql.functions import col, explode


def get_node_list(df):
    df_ant = df.select(explode(col("`antecedent`")).alias("node"))
    df_con = df.select(explode(col("`consequent`")).alias("node"))

    distinct_nodes_df = df_ant.union(df_con).distinct()
    return list([int(row.node) for row in distinct_nodes_df.collect()])


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


def get_properties(dataset, type):
    properties = {}
    property_col = 1 if type=="node" else 3

    # Find node labels and their default property
    with open(f'./data/datasets/{dataset}/{dataset}_{type}_types.csv') as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        
        # skip header line
        next(csv_reader)

        for row in csv_reader:
            properties[str(row[0])] = [item.strip() for item in row[property_col].replace("[", "").replace("]", "").split(",")]

    return properties