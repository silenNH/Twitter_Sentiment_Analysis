from pyspark.sql.session import SparkSession
from pyspark.sql.functions import *
import json
import sys
from pyspark.sql.types import * 
from datetime import datetime
import pytz
from afinn import Afinn

#Command line:
#PYSPARK_PYTHON=python3 spark-3.1.2-bin-hadoop3.2/bin/spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.1.2 KafkaConsumer/KafkaConsumerOldV10.py 
#PYSPARK_PYTHON=python3 /opt/bitnami/spark/bin/spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.1.2 /opt/bitnami/spark/work/KafkaConsumerOldV10.py  

#Define the function (UDF) for date extraction
def getDate(x):
    if x is not None:
        return str(datetime.strptime(x,'%a %b %d %H:%M:%S +0000 %Y').replace(tzinfo=pytz.UTC).strftime("%Y-%m-%d %H:%M:%S"))
    else:
        return None

#Define the function (UDF) to estimate the sentimentof the tweet
def getSentiment(text):
    return  afinn.score(text)

# define the input and output topics of Kafka
Kafka_Input_Topic="twitter"
Kafka_Output_Topic_Result="SparkResult"
Kafka_Output_Topic_rawData="SparkrawData"
Kafka_Input_Server="broker:9092"
Kafka_Output_Server="broker:9092"

if __name__ == "__main__":

    #Create Afinn object 
    afinn=Afinn()

    # Define the structure of the input streaming data
    schema=StructType([
        StructField("text", StringType(),True),
        StructField("created_at",StringType(),True),
        StructField("id", IntegerType(),True),
        StructField("followers_count", IntegerType(),True)
    ])

    #Create a SparkSession
    spark=SparkSession.builder.appName("TwitterSentiTest").getOrCreate()
    # Set logger input to ERROR in order to avoid showing all info messages
    spark.sparkContext.setLogLevel("ERROR")
    # Read the stream from Kafka; reading latest offset since the information reated in the early past are important and old data not
    kafka_rawdData_df=spark.readStream.format("kafka").option("kafka.bootstrap.servers", Kafka_Input_Server).option("subscribe", Kafka_Input_Topic).option("startingOffsets", "latest").load()
    
    #Cast the Kafka value in a string
    kafka__rawData_df_string=kafka_rawdData_df.selectExpr("CAST(value AS STRING)")
    #kafka_df_string=kafka_df.selectExpr("CAST(value AS STRING)", "timestamp")  # if timestamp is needed

    #Get the right table schema via conversion (from_json)
    kafka_df=kafka__rawData_df_string.select(from_json(col("value"), schema).alias("data")).select("data.*")

    #Create column event_data
    #apply UDF getDate
    udf_date=udf(getDate, StringType())
    #Add a column with the event_data 
    tweets_table_withEventDate= kafka_df.withColumn("event_date", to_utc_timestamp(udf_date("created_at"),"UTC"))

    #Get Sentiment 
    #apply UDF getSentiment 
    udf_sentiment=udf(getSentiment,DoubleType())
    #Add a column with the Sentiment per Tweet
    tweets_table_withEventDate_withSentiment=tweets_table_withEventDate.withColumn("Sentiment", udf_sentiment("text"))

    #Useing Window operator
    #windowedCounts=tweets_table_withEventDate_withSentiment.withWatermark("event_date", "5 minutes").groupBy(window(col("event_date"), "3 minutes", "20 seconds")).agg(avg(col("Sentiment")).alias("AVG_Sentiment"), count('*'))
    windowedCounts=tweets_table_withEventDate_withSentiment.withWatermark("event_date", "5 minutes").groupBy(window(col("event_date"), "3 minutes", "20 seconds")).agg(avg(col("Sentiment")).alias("AVG_Sentiment")).select("window.end", "AVG_Sentiment")
    windowedCounts=windowedCounts.withColumn("UNIX_TIMESTAMP", unix_timestamp("end")).select("end","UNIX_TIMESTAMP","AVG_Sentiment")

    #query_date=tweets_table_withEventDate_withSentiment.writeStream.outputMode("append").format("console").start()
    query_date=windowedCounts.writeStream.outputMode("complete").format("console").start()
    
    
    #df_rawData_forKAFKA=tweets_table_withEventDate_withSentiment.withColumn("key", lit(1))
    
    df_rawData_forKAFKA=tweets_table_withEventDate_withSentiment.withColumn("key", lit(1))
    """
    df_rawData_forKAFKA=tweets_table_withEventDate_withSentiment.withColumn("key", lit(1))\
        .withColumn("value", concat(col("text"), lit(","),\
        col("followers_count"), lit(","), col("event_date"), lit(","), col("Sentiment")))
    """

    dfForKafka_rawData_transmitted= df_rawData_forKAFKA\
        .selectExpr("CAST(key as STRING)","to_json(struct(*)) AS value")\
        .writeStream\
        .format("kafka")\
        .option("kafka.bootstrap.servers", Kafka_Output_Server)\
        .option("topic", Kafka_Output_Topic_rawData)\
        .trigger(processingTime="20 seconds")\
        .outputMode("append")\
        .option("checkpointLocation","/home/niels/Documents/Twitter_Sentiment/CheckpointData/rawData")\
        .start()


    #df_avgResult_forKAFKA=windowedCounts.withColumn("key", lit(2))
    
    df_avgResult_forKAFKA=windowedCounts.withColumn("key", lit(2))
    """
    df_avgResult_forKAFKA=windowedCounts.withColumn("key", lit(2))\
        .withColumn("value", concat(lit("{'window': '"), col("window").cast("string"), lit("', 'AVG_Sentiment: '"), col("AVG_Sentiment").cast("string"),\
         lit("', 'count(1): '"), col("count(1)").cast("string"), lit("'}")))
    """

    dfForKafka_avgResult_transmitted=df_avgResult_forKAFKA\
        .selectExpr("CAST(key as STRING)", "to_json(struct(*)) AS value")\
        .writeStream\
        .format("kafka")\
        .option("kafka.bootstrap.servers", Kafka_Output_Server)\
        .option("topic", Kafka_Output_Topic_Result)\
        .trigger(processingTime="20 seconds")\
        .outputMode("update")\
        .option("checkpointLocation","/home/niels/Documents/Twitter_Sentiment/CheckpointData")\
        .start()
    
    dfForKafka_rawData_transmitted.awaitTermination()
    query_date.awaitTermination()
    dfForKafka_avgResult_transmitted.awaitTermination()
