import csv


def find_default_property(dataset, label):
    property_list = ["name","title","label","id","uid","username","code"]

    with open(f'./data/datasets/{dataset}/{dataset}_node_types.csv') as csv_file:
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

def get_node_properties(dataset):

    node_labels = []
    default_properties = {}

    # Find node labels and their default property
    with open(f'./data/datasets/{dataset}/node_labels.csv') as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            if str(row[0]) == "label": continue
            node_labels.append(str(row[0]))
    
    for x in node_labels:
        default_properties[x] = find_default_property(dataset, label=x)

    return node_labels, default_properties