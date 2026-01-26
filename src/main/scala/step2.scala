import org.apache.spark.sql.{SparkSession, DataFrame}
import org.apache.spark.sql.functions._

object Step2Neo4jToBaskets {

  def main(args: Array[String]): Unit = {

    //val neo4jUrl  = "neo4j://localhost:7687"
    val neo4jUrl = "bolt://localhost:7687"
    val neo4jUser = "neo4j"
    val neo4jPass = "Neo4j123"

    val spark = SparkSession.builder()
      .appName("HY562-Step2-Neo4j-To-Baskets")
      .master("local[*]")
      .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")

    // Read relationships as rows: (source)-[APPEARED_IN]->(target)
    val df: DataFrame =
        spark.read
      .format("org.neo4j.spark.DataSource")
        .option("url", neo4jUrl)
        .option("authentication.type", "basic")
        .option("authentication.basic.username", neo4jUser)
        .option("authentication.basic.password", neo4jPass)
        .option("relationship", "APPEARED_IN")
        .option("relationship.source.labels", ":Character")
        .option("relationship.target.labels", ":Film")
        .load()

    println("Sample rows from Neo4j:")
    df.show(5, truncate = false)

    df.printSchema()

    // CORRECT
    val baskets =
      df.groupBy(col("`target.title`").as("film"))
        .agg(collect_set(col("`source.name`")).as("items"))
        .filter(size(col("items")) > 1)

    println("Baskets (film -> items):")
    baskets.show(20, truncate = false)

    println(s"Number of baskets: ${baskets.count()}")

    // Save to disk (optional)
    baskets.write.mode("overwrite").json("output/baskets_json")

    spark.stop()
  }
}

