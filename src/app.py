import atexit
import streamlit as st
from pathlib import Path
from summarization import *
from dotenv import load_dotenv
from neo4j import Neo4jManager
from spark_utils import init_spark, execute_query


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

# Select Dataset
dataset_path = Path('./data/datasets')
dataset_options = [f.name for f in dataset_path.iterdir() if f.is_dir()]
dataset_selection = st.selectbox("Select dataset", dataset_options)


if st.button("Select"):
    st.session_state.current_dataset = dataset_selection
    with st.spinner("Loading Neo4j..."):
        neo4j_manager.load(st.session_state.current_dataset)
        neo4j_manager.start()
        st.session_state.dataset_loaded = True


if st.session_state.dataset_loaded:
    st.write(f"Loaded dataset: {st.session_state.current_dataset}")

    general_tab, personalized_tab = st.tabs([
        "General Summary", 
        "Personalized Summary"
    ])

    with general_tab:
        test_container = st.container()
        with test_container:
            st.write("ta arxidia mou einai megala einai san tou king kong")
            st.write("big bottle boys")
    
    # Personalized Summary Tab
    with personalized_tab:
        mode_options = ["Strict", "Loose", "Association"]
        selection = st.selectbox("Select summarization mode", mode_options)
        st.write(f"Selected mode: {selection}")

        mode = None
        match selection:
            case "Strict": mode = Mode.STRICT
            case "Loose": mode = Mode.LOOSE
            case "Association": mode = Mode.ASSOCIATION
            case _: mode = None
        print(f"(selection, mode): ({selection},{mode})")

        if st.button("User Query"):
            filter_graph_based_on_user(None, mode)

    if st.button("EINIA 7:47 to PRO🐴"):
        st.balloons()
        print(execute_query(summary_manager.spark, "MATCH (p) return p limit 15"))


# Cleanup at exit
def cleanup():
    print("🧹 Cleaning up: Stopping Spark and Neo4j...")
    summary_manager.spark.stop()
    neo4j_manager.stop()

atexit.register(cleanup)