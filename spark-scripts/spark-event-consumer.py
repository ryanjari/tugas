from pyspark.sql.functions import *
from pyspark.sql.types import *
from pyspark.sql import SparkSession
from dotenv import load_dotenv
from pathlib import Path
import os

# Load environment variables
dotenv_path = Path('/opt/app/.env')
load_dotenv(dotenv_path=dotenv_path)

# Initialize variables
spark_hostname = os.getenv('SPARK_MASTER_HOST_NAME')
spark_port = os.getenv('SPARK_MASTER_PORT')
kafka_host = os.getenv('KAFKA_HOST')
kafka_topic = os.getenv('KAFKA_TOPIC_NAME')
spark_host = f'spark://{spark_hostname}:{spark_port}'

# Create spark session
spark = (
    SparkSession
    .builder
    .appName('DibimbingStreamingConsumer')
    .master(spark_host)
    .getOrCreate()
)
spark.sparkContext.setLogLevel('WARN')

# Create schema
schema = StructType(
    [
        StructField('order_id', StringType(), True),
        StructField('customer_id', IntegerType(), True),
        StructField('furniture', StringType(), True),
        StructField('color', StringType(), True),
        StructField('price', IntegerType(), True),
        StructField('ts', StringType(), True),
    ]
)

# Read from kafka
streaming = (
    spark.readStream.format('kafka')
    .option('kafka.bootstrap.servers', f'{kafka_host}:9092')
    .option('subscribe', kafka_topic)
    .option('startingOffsets', 'latest')
    .load()
)

# Get 'value', deserialize json, and convert timestamp using function from_unixtime
json_df = (
    streaming
    .selectExpr('CAST(value AS STRING) as value')
    .withColumn('value', from_json('value', schema)).select('value.*')
    .withColumn('ts', from_unixtime('ts').cast('timestamp'))
)

# Aggregate data with group window 1 day
total_per_day = (
    json_df
    .withWatermark('ts', '3 minutes')
    .groupBy(window('ts', '1 day').alias('day'))
    .agg(
        sum('price').alias('total_price'),
        count('order_id').alias('total_order')
    )
)

# Write stream to console with complete mode and checkpoint
(
    total_per_day
    .writeStream
    .format('console')
    .trigger(processingTime='1 minutes')
    .outputMode('complete')
    .option('checkpointlocation', '/logs')
    .start() 
    .awaitTermination()
)

'''
# Write stream to parquet without forachBatch
(
    json_df
    .writeStream
    .format('parquet')
    .partitionBy('ts')
    .outputMode('append') # Append only
    .option('path', '/spark-scripts/data')
    .option('checkpointLocation','/logs')
    .trigger(processingTime='1 minutes')
    .start()
    .awaitTermination()
)
'''

''' try foreachBatch parquet
def write_to_parquet(json_df, epoch_id):
    CWD = os.getcwd()
    DATA_PATH = os.path.join(CWD, '/')
    (
        json_df
        .withWatermark('ts', '3 minutes')
        .groupBy(window('ts', '1 day').alias('day'))
        .agg(
            sum('price').alias('total_price'),
            count('order_id').alias('total_order')
        )
        .write
        .parquet(path=CWD, mode='overwrite')
    )

(
    json_df
    .writeStream
    .foreachBatch(write_to_parquet)
    .trigger(processingTime='2 minutes')
    .option('checkpointLocation','/logs')
    .start()
    .awaitTermination()
)
'''
