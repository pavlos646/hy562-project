### NOTHING :) 🙃 ###

```py
def visualize_subgraph(df):

    if df is None:
        st.warning("No graph data to visualize.")
        return

    # Collect data from Spark to Python
    # (Limit to avoid browser crash if graph is huge)
    try:
        rows = df.limit(100).collect()
    except Exception as e:
        st.error(f"Error collecting graph data: {e}")
        return

    unique_nodes = set()
    edges = []
    
    # 2. Iterate through each path
    for row in rows:
        path_nodes = row['path_nodes']      # e.g. [Movie, Actor, Movie]
        rels = row['relationships']         # e.g. [APPEARED_IN, APPEARED_IN]
        
        # Check if we have valid data
        if not path_nodes or not rels:
            continue

        # 3. Construct Edges (Node[i] -- Rel[i] --> Node[i+1])
        for i in range(len(rels)):
            source = str(path_nodes[i])
            target = str(path_nodes[i+1])
            label = str(rels[i])
            
            # Add to Node Set (to ensure uniqueness)
            unique_nodes.add(source)
            unique_nodes.add(target)
            
            # Create Edge Object
            # Using specific IDs helps prevent duplicate edges if needed, 
            # but here we just append.
            edges.append(Edge(
                source=source,
                target=target,
                label=label,	#???
                color="#888888",
                type="CURVE_SMOOTH" 
            ))

    # 4. Create Node Objects
    nodes = []
    for n in unique_nodes:
        nodes.append(Node(
            id=n,
            label=n,  #???
            size=20,
            shape="dot",
            color="#FF4B4B" # Streamlit Red
        ))

    # 5. Configure & Render ????
    config = Config(
        width="100%",
        height=600,
        directed=True, 
        physics=True, 
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6"
    )

    return agraph(nodes=nodes, edges=edges, config=config)
    ```


init_object  --> spark 
dataset --> load_dataset --> node_labels, default_properties, node_count


GENERAL SUMMARY:
association --> id_mappings, association_rules
id_mappings, association_rules           --> general_summarization --> subgraph
id_mappings, association_rules, subgraph --> verbalization         --> verbalization_text

PERSONALIZED SUMMARY:
interests, mode --> personalized_summary --> subgraph
id_mappings, association_rulesm subgraph --> verbalization --> verbalization_text



import plotly.express as px
import pandas as pd

def visualize_heatmap(spark_df):
    # 1. Convert to Pandas
    df = spark_df.limit(500).toPandas()
    
    # 2. Extract Source-Target-Strength
    # We need to flatten the paths into simple (Source, Target, Count/Type) rows
    data = []
    for row in df.itertuples():
        nodes = row.path_nodes
        rels = row.relationships
        for i in range(len(rels)):
            # You might want to count frequency if there are duplicates
            data.append({
                "Source": str(nodes[i]),
                "Target": str(nodes[i+1]),
                "Strength": 1 # Or use a real metric if available
            })
            
    plot_df = pd.DataFrame(data)
    
    # 3. Create Heatmap
    # We aggregate to handle duplicates (Source->Target appearing multiple times)
    matrix_df = plot_df.groupby(["Source", "Target"]).count().reset_index()
    
    fig = px.density_heatmap(
        matrix_df, 
        x="Source", 
        y="Target", 
        z="Strength", 
        color_continuous_scale="Viridis",
        title="Relationship Density Matrix"
    )
    
    st.plotly_chart(fig, use_container_width=True)





    import streamlit as st
import streamlit.components.v1 as components
from neo4j_viz import VisualizationGraph, Node, Relationship
import pandas as pd

def visualize_path_dataframe(df):
    """
    Transforms a DataFrame with 'path_nodes' and 'relationships' columns
    into an interactive Neo4j Visualization Graph.
    """
    
    # 1. Convert Spark DF to Pandas if necessary
    # (If it's already Pandas, this line does nothing)
    try:
        pdf = df.toPandas()
    except AttributeError:
        pdf = df

    # 2. Containers for Unique Elements
    # We use a dict for nodes to prevent duplicates: { "Luke": Node(...) }
    unique_nodes = {} 
    rels_list = []
    
    # 3. Iterate through every row (every path)
    for _, row in pdf.iterrows():
        path_nodes = row['path_nodes']      # e.g., ["Empire", "Luke", "A New Hope"]
        path_rels = row['relationships']    # e.g., ["APPEARED_IN", "APPEARED_IN"]
        
        # Safety check: relationships list should be 1 shorter than nodes list
        if len(path_nodes) < 2: continue

        # --- A. Process Nodes ---
        for node_name in path_nodes:
            node_name = str(node_name) # Ensure string format
            
            # Only create the node if we haven't seen it yet
            if node_name not in unique_nodes:
                # You can customize 'labels' or 'properties' if you have that info
                unique_nodes[node_name] = Node(
                    id=node_name,          # Use name as the unique ID
                    labels=["Entity"],     # Default label (optional)
                    properties={"name": node_name},
                    size=20,               # Default size
                    caption="name"         # Tell viz to display the 'name' property
                )

        # --- B. Process Relationships ---
        # Iterate through the edges: Node[i] -[Rel[i]]-> Node[i+1]
        for i in range(len(path_rels)):
            source_id = str(path_nodes[i])
            target_id = str(path_nodes[i+1])
            rel_type = str(path_rels[i])
            
            # Create unique ID for the edge to avoid React key issues
            # Format: Source_Type_Target
            rel_id = f"{source_id}_{rel_type}_{target_id}"
            
            rels_list.append(Relationship(
                id=rel_id,
                start_node_id=source_id,
                end_node_id=target_id,
                type=rel_type,
                properties={"type": rel_type}
            ))

    # 4. Instantiate the Visualization
    # Convert dict values to a list of Node objects
    viz = VisualizationGraph(
        nodes=list(unique_nodes.values()), 
        relationships=rels_list
    )
    
    # 5. Render
    return viz

# --- USAGE IN STREAMLIT ---
# Assuming 'subgraph_df' is your dataframe
if st.button("Visualize with Neo4j Viz"):
    
    # 1. Create the Viz Object
    viz_graph = visualize_path_dataframe(subgraph_df)
    
    # 2. Render HTML
    html_source = viz_graph.render()
    
    # 3. Embed in Streamlit
    st.subheader("Interactive Neo4j Visualization")
    components.html(html_source, height=700, scrolling=True)