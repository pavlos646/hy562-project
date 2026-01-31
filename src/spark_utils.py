from pyspark.sql import SparkSession


def execute_query(spark, query):
    return spark.read \
        .format("org.neo4j.spark.DataSource") \
        .option("query", query) \
        .load()

def init_spark():
    # TODO: maybe get all these from a config file
    neo4j_url = "bolt://[0:0:0:0:0:0:0:0]:7687"
    neo4j_user = "neo4j"
    neo4j_pass = "password"

    # init spark
    spark = SparkSession.builder \
        .appName("HY562-Step2-Neo4j-To-Baskets") \
        .master("local[*]") \
        .config("spark.driver.memory", "8g") \
        .config("spark.jars.packages", "org.neo4j:neo4j-connector-apache-spark_2.13:5.4.0_for_spark_3") \
        .config("neo4j.url", neo4j_url) \
        .config("neo4j.authentication.type", "basic") \
        .config("neo4j.authentication.basic.username", neo4j_user) \
        .config("neo4j.authentication.basic.password", neo4j_pass) \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")

    print(f"Connecting to {neo4j_url}...")

    return spark