import atexit
import streamlit as st
from pathlib import Path
from summarization import *
from dotenv import load_dotenv
from neo4j_viz import Node, Relationship, VisualizationGraph
from neo4j_utils import Neo4jManager, wait_for_neo4j
from spark_utils import init_spark, execute_query
import streamlit.components.v1 as components


def visualize_subgraph(sm: SummarizationManager):
    if sm.subgraph is None:
        st.warning("No graph data to visualize.")
        return

    try:
        rows = sm.subgraph.collect()
    except Exception as e:
        st.error(f"Error collecting graph data: {e}")
        return

    viz_nodes = {}
    viz_relationships = []

    for row in rows:
        path_nodes = row['path_nodes']  # list of display names
        rels = row['relationships']     # list of relationship types
        
        if not path_nodes or not rels:
            continue

        # Create Node objects
        for node_string in path_nodes:
            if node_string not in viz_nodes:
                # e.g. Character:Anakin Skywalker
                node_type, node_name = node_string.split(':')

                viz_nodes[node_string] = Node(
                    id=node_name,
                    caption=node_type,
                    size=15,
                    properties={
                        "Type": node_type
                    }
                )

        # Create Relationship objects
        for i in range(len(rels)):
            viz_relationships.append(Relationship(
                source=path_nodes[i].split(':')[1],
                target=path_nodes[i+1].split(':')[1],
                caption=rels[i],
                properties={
                    "Type": rels[i]
                }
            ))

    vg = VisualizationGraph(
        nodes=list(viz_nodes.values()), 
        relationships=viz_relationships
    )
    
    # Color nodes by their caption (label)
    vg.color_nodes(field="caption")
    
    # Check what engine to use based on the size of the subgraph
    renderer = "canvas" if (sm.subgraph.count()<100) else "webgl"

    html_content = vg.render(renderer=renderer, width="100%", height="600px")
    components.html(html_content.data, height=650, scrolling=True)


@st.cache_resource
def initialize_app():
    load_dotenv()
    neo4j_manager = Neo4jManager(
        neo4j_home="../neo4j-community-4.4.46", 
        dataset_home="./data/datasets/"
    )
    spark = init_spark()
    general_sm = SummarizationManager(spark)
    personalized_sm = SummarizationManager(spark)
    return general_sm, personalized_sm, neo4j_manager

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(
    page_title="Semantic PG Summarization",
    page_icon="📝",
    layout="centered"
)

# -----------------------------
# Header
# -----------------------------
st.title("📝 Semantic PG Summarization")
st.markdown(
    """
    Select a **dataset** and **personalization mode** to generate 
    a concise, interpretive summary based on the graph data.
    """
)

general_sm, personalized_sm, neo4j_manager = initialize_app()

if "dataset_loaded" not in st.session_state:
    st.session_state.dataset_loaded = None
if "current_dataset" not in st.session_state:
    st.session_state.current_dataset = ""
if "general_summary_ready" not in st.session_state:
    st.session_state.general_summary_ready = False
if "personalized_summary_ready" not in st.session_state:
    st.session_state.personalized_summary_ready = False
if "personalized_cypher_query" not in st.session_state:
    st.session_state.personalized_cypher_query = False
if "user_interests" not in st.session_state:
    st.session_state.user_interests = {}

# Select Dataset
dataset_path = Path('./data/datasets')
dataset_options = [f.name for f in dataset_path.iterdir() if f.is_dir()]
default_index = dataset_options.index("star-wars")
dataset_selection = st.selectbox("Select dataset", dataset_options, index=default_index)


if st.button("Select"):
    st.session_state.current_dataset = dataset_selection
    with st.spinner("Loading Neo4j..."):
        neo4j_manager.load(st.session_state.current_dataset)
        neo4j_manager.start()
        
        if wait_for_neo4j():
            general_sm.load(st.session_state.current_dataset)
            personalized_sm.load(st.session_state.current_dataset)
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
                cypher_query = general_summarization(general_sm)
                st.session_state.general_cypher_query = cypher_query
                st.session_state.general_summary_ready = True


        if st.session_state.general_summary_ready:
            st.write("### Subgraph")
            st.write("**Cypher Query**")
            st.code(st.session_state.general_cypher_query, language="cypher")
            st.write("**Description**")
            st.write(general_sm.subgraph)
            
            
            visualize_subgraph(general_sm)

            if st.button("Verbalize Summary"):
                with st.spinner("Loading..."):
                    summary = get_verbalization(general_sm)
                    st.write("### Summary")
                    st.markdown(summary, text_alignment="justify")


    
    # Personalized Summary Tab
    with personalized_tab:
        mode_options = ["Strict", "Loose", "Association"]
        selection = st.selectbox("Select summarization mode", mode_options)


        with st.form("interests_form", clear_on_submit=True):

            st.write("#### Select interests")

            col_left, col_right = st.columns([1, 2])
            with col_left:
                node_options = get_properties(personalized_sm.dataset, "node")
                node_selection = st.selectbox("Node Type", node_options)
            with col_right:
                user_text = st.text_area("Node Name", placeholder="Enter entity name here...")

            submitted = st.form_submit_button("Select")

            if submitted:
                prop_name = personalized_sm.default_properties[node_selection]
                query = f"""
                    MATCH (n:{node_selection})
                    WHERE toLower(n.{prop_name})=toLower('{user_text}')
                    RETURN COUNT(n) AS node_count, collect(n.{prop_name})[0] AS actual_name
                """
                tmp_res = execute_query(personalized_sm.spark, query).collect()[0]
                if int(tmp_res["node_count"]) >= 1:
                    st.toast("Selection Saved!", icon='✅')
                    # MAYBE: have as option to save in .json file :)
                    db_name = tmp_res["actual_name"]
                    st.session_state.user_interests.setdefault(node_selection, []).append(db_name)
                else:
                    st.toast(f"{node_selection} not found!", icon='❌')

            st.write("**Interests**")
            st.write(st.session_state.user_interests)


        mode = None
        match selection:
            case "Strict": mode = Mode.STRICT
            case "Loose": mode = Mode.LOOSE
            case "Association": mode = Mode.ASSOCIATION
            case _: mode = None

        if st.button("Generate Summary", key="personalized"):
            with st.spinner("Loading..."):
                print("USER INTERESTS: ")
                print(st.session_state.user_interests)
                cypher_query = filter_graph_based_on_user(personalized_sm, st.session_state.user_interests, mode)
                st.session_state.personalized_cypher_query = cypher_query
                st.session_state.personalized_summary_ready = True

        if st.session_state.personalized_summary_ready:
            st.write("### Subgraph")
            st.write("**Cypher Query**")
            st.code(st.session_state.personalized_cypher_query, language="cypher")
            st.write("**Description**")
            st.write(personalized_sm.subgraph)

            visualize_subgraph(personalized_sm)

            if st.button("Verbalize Summary", key="personalized-verbalize"):
                with st.spinner("Loading..."):
                    # we already have subgraph set, we need id_mappings, association_rules
                    association(personalized_sm)
                    summary = get_verbalization(personalized_sm)
                    st.write("### Summary")
                    st.markdown(summary, text_alignment="justify")

    with st.sidebar:
        st.header("🎯 Current Interests")
        if not st.session_state.user_interests:
            st.info("No interests selected yet.")
        else:
            for label, names in st.session_state.user_interests.items():
                st.subheader(f"{label}")
                for name in names:
                    # Use a small 'caption' or bullet points
                    st.write(f"- {name}")
                st.markdown("---")
            
            if st.button("Clear All"):
                st.session_state.user_interests = {}
                st.rerun()
            

# Cleanup at exit
def cleanup():
    print("🧹 Cleaning up: Stopping Spark and Neo4j...")
    general_sm.spark.stop()
    personalized_sm.spark.stop()
    neo4j_manager.stop()

atexit.register(cleanup)