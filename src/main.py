from pyspark.sql import SparkSession
from pyspark.sql.functions import col, collect_set, size

def main():
    # Configuration
    # Ensure this address is accessible from your docker/local environment
    neo4j_url = "bolt://[0:0:0:0:0:0:0:0]:7687" 
    neo4j_user = "neo4j"
    neo4j_pass = "password"

    # Initialize Spark Session
    # Note: The connector package is injected via spark-submit in run.sh
    spark = SparkSession.builder \
        .appName("HY562-Step2-Neo4j-To-Baskets") \
        .master("local[*]") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")

    print(f"Connecting to {neo4j_url}...")

    # Read relationships
    df = spark.read \
        .format("org.neo4j.spark.DataSource") \
        .option("url", neo4j_url) \
        .option("authentication.type", "basic") \
        .option("authentication.basic.username", neo4j_user) \
        .option("authentication.basic.password", neo4j_pass) \
        .option("relationship", "APPEARED_IN") \
        .option("relationship.source.labels", ":Character") \
        .option("relationship.target.labels", ":Film") \
        .load()

    # Logic
    baskets = df.groupBy(col("`target.title`").alias("film")) \
        .agg(collect_set(col("`source.name`")).alias("items")) \
        .filter(size(col("items")) > 1)

    print("Baskets (film -> items):")
    baskets.show(20, truncate=False)

    print(f"Number of baskets: {baskets.count()}")

    # Save to disk
    baskets.write.mode("overwrite").json("output/baskets_json")

    spark.stop()

if __name__ == "__main__":
    main()