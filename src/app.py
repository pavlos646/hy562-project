import atexit
import streamlit as st
from streamlit_agraph import Edge, Node, Config, agraph
from pathlib import Path
from summarization import *
from dotenv import load_dotenv
from neo4j_utils import Neo4jManager, wait_for_neo4j
from spark_utils import init_spark, execute_query

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
        height=800,
        directed=True, 
        physics=True, 
        hierarchical=False,
        nodeHighlightBehavior=True,
        nodeSpacing=200,   
        sortMethod="hubsize",
        gravity=-5000,      
        springLength=200,  
        springConstant=0.05, 
        highlightColor="#F7A7A6"
    )

    return agraph(nodes=nodes, edges=edges, config=config)


@st.cache_resource
def initialize_app():
    load_dotenv()
    neo4j_manager = Neo4jManager(
        neo4j_home="../neo4j-community-4.4.46", 
        dataset_home="./data/datasets/"
    )
    summary_manager = SummarizationManager(spark=init_spark())
    return summary_manager, neo4j_manager

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(
    page_title="Semantic PG Summarization",
    page_icon="🧠",
    layout="centered"
)

# -----------------------------
# Header
# -----------------------------
st.title("🧠 Semantic PG Summarization")
st.markdown(
    """
    Επιλέξτε **dataset** και **τρόπο εξατομίκευσης** για να παραχθεί
    μια συνοπτική, ερμηνευτική περιγραφή βασισμένη στα δεδομένα.
    """
)

summary_manager, neo4j_manager = initialize_app()

if "dataset_loaded" not in st.session_state:
    st.session_state.dataset_loaded = None
if "current_dataset" not in st.session_state:
    st.session_state.current_dataset = ""
if "general_summary_ready" not in st.session_state:
    st.session_state.general_summary_ready = False
if "personalized_summary_ready" not in st.session_state:
    st.session_state.personalized_summary_ready = False

# Select Dataset
dataset_path = Path('./data/datasets')
dataset_options = [f.name for f in dataset_path.iterdir() if f.is_dir()]
dataset_selection = st.selectbox("Select dataset", dataset_options)


if st.button("Select"):
    st.session_state.current_dataset = dataset_selection
    with st.spinner("Loading Neo4j..."):
        neo4j_manager.load(st.session_state.current_dataset)
        neo4j_manager.start()
        
        if wait_for_neo4j():
            summary_manager.load(st.session_state.current_dataset)
            st.session_state.dataset_loaded = True


if st.session_state.dataset_loaded:
    st.write(f"Loaded dataset: {st.session_state.current_dataset}")

    general_tab, personalized_tab = st.tabs([
        "General Summary", 
        "Personalized Summary"
    ])

    with general_tab:
        if st.button("Generate Summary", key="general"):
            with st.spinner("Loading..."):
                general_summarization(summary_manager)
                st.session_state.general_summary_ready = True


        if st.session_state.general_summary_ready:
            st.write("### Subgraph")
            st.write(summary_manager.subgraph)
            visualize_subgraph(summary_manager.subgraph)

            if st.button("Verbalize Summary"):
                with st.spinner("Loading..."):
                    summary = get_verbalization(summary_manager)
                    st.write("### Summary")
                    st.markdown(summary, text_alignment="justify")


    
    # Personalized Summary Tab
    with personalized_tab:
        mode_options = ["Strict", "Loose", "Association"]
        selection = st.selectbox("Select summarization mode", mode_options)
        # st.write(f"Selected mode: {selection}") #TODO: after the load set it

        mode = None
        match selection:
            case "Strict": mode = Mode.STRICT
            case "Loose": mode = Mode.LOOSE
            case "Association": mode = Mode.ASSOCIATION
            case _: mode = None

        if st.button("Generate Summary", key="personalized"):
            with st.spinner("Loading..."):
                filter_graph_based_on_user(summary_manager, mode)
                st.session_state.personalized_summary_ready = True

        if st.session_state.personalized_summary_ready:
            st.write("### Subgraph")
            st.write(summary_manager.subgraph)
            # visualize_subgraph(summary_manager.subgraph)


# Cleanup at exit
def cleanup():
    print("🧹 Cleaning up: Stopping Spark and Neo4j...")
    summary_manager.spark.stop()
    neo4j_manager.stop()

atexit.register(cleanup)