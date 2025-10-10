package tutorial

object Main {
  def main(args: Array[String]): Unit = {
    import org.apache.spark.sql.SparkSession
    import org.apache.spark.sql.functions._

    val spark = SparkSession.builder()
      .appName("Lab2_Example")
      .master("local[*]") // use all CPU cores on your machine - hope your PC can handle it :)
      .getOrCreate()

    spark.sparkContext.setLogLevel("WARN") // to reduce log spam


    val sc = spark.sparkContext

    val numbers = sc.parallelize(1 to 10)

    println("Original numbers:")
    numbers.collect().foreach(println)

    // transformation
    val squared = numbers.map(x => x * x)
    println("Squared numbers:")
    squared.collect().foreach(println)

    // action
    val sum = numbers.reduce(_ + _)
    println(s"Sum of numbers: $sum")

    // filter
    val evens = numbers.filter(_ % 2 == 0)
    println("Even numbers:")
    evens.collect().foreach(println)

    // df
    import spark.implicits._

    // a small df
    val df = Seq(
      ("Alice", 25),
      ("Bob", 30),
      ("John", 27),
      ("Sophia", 25)
    ).toDF("name", "age")

    df.show() // prints the df

    // filter
    val adults = df.filter($"age" > 28)
    println("People older than 28:")
    adults.show()

    // adding a new column
    val withDecade = df.withColumn("age_in_10_years", $"age" + 10)
    println("With new column:")
    withDecade.show()

    // aggrecation
    println("Average age:")
    df.agg(avg("age")).show()


    // write df to disk
    withDecade.write.mode("overwrite").csv("output/people_csv")

    // read the df
    val readBack = spark.read.option("header", "false").csv("output/people_csv")
    println("Read back from CSV:")
    readBack.show()

    // always stop spak
    spark.stop()
    println("=== Spark session stopped ===")

  }
}
