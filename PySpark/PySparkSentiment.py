#import libraries
from pyspark.sql.session import SparkSession
from pyspark.sql.functions import *
import json
import sys
from pyspark.sql.types import * 
from datetime import datetime
import pytz
from afinn import Afinn


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
    windowedCounts=tweets_table_withEventDate_withSentiment.withWatermark("event_date", "1 minutes").groupBy(window(col("event_date"), "1 minutes", "20 seconds")).agg(avg(col("Sentiment")).alias("AVG_Sentiment")).select("window.end", "AVG_Sentiment")
    
    # Add a UNIX_Timestamp for influxdb processing
    windowedCounts=windowedCounts.withColumn("UNIX_TIMESTAMP", unix_timestamp("end")).select("end","UNIX_TIMESTAMP","AVG_Sentiment")

    #Create Console output 
    query_windowedCounts=windowedCounts.writeStream.outputMode("complete").format("console").start()
        
    
    # If the raw data is required inclusive sentiment uncomment the following code part as well as the lower command: dfForKafka_rawData_transmitted.awaitTermination()
    """
    # Add a constant key to the data stream 
    df_rawData_forKAFKA=tweets_table_withEventDate_withSentiment.withColumn("key", lit(1))

    #Create a stream to Kafka to the topic "SparkrawData"
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
    """
    # Add a constant key to the data stream 
    df_avgResult_forKAFKA=windowedCounts.withColumn("key", lit(2))
    
    # Create a stream to Kafka to the Topic "SparkResult"
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
    
    # uncomment if you want to see the raw data inclusive sentiment
    """
    dfForKafka_rawData_transmitted.awaitTermination()
    """
    #Await termination for console output 
    query_windowedCounts.awaitTermination()
    #Await termination for Kafka Stream 
    dfForKafka_avgResult_transmitted.awaitTermination()
