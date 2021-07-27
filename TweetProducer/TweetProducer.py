# import libraries
import tweepy
from tweepy import OAuthHandler
from tweepy import Stream
from tweepy.streaming import StreamListener
import json
import pykafka
from configparser import ConfigParser


class TweetListener(StreamListener):
	def __init__(self):
		self.client = pykafka.KafkaClient("broker:9092")
		self.producer = self.client.topics[bytes('twitter','ascii')].get_producer()

	# Filter out the necessary information to sent to Kafka Topic twitter: 
	# 1) Text 2) created_at 3) if 4) followers count 5) text 
	# The text + a tag ________ENDE____ is written in the console 
	def on_data(self, data):
		try:
			json_data = json.loads(data)
			send_data = '{}'
			json_send_data = json.loads(send_data)			
			json_send_data['text'] = json_data['text']
			json_send_data['created_at']= json_data['created_at']
			json_send_data_user=json_data['user']
			json_send_data["id"]=json_send_data_user["id"]
			json_send_data["followers_count"]=json_send_data_user["followers_count"]
			print(json_send_data['text'], "___________END_____________")
			self.producer.produce(bytes(json.dumps(json_send_data),'ascii'))
			return True
		except KeyError:
			return True

	def on_error(self, status):
		print(status)
		return True

if __name__ == "__main__":
	#Initialize the config parser 
	config=ConfigParser()
	file='./config.ini'
	config.read(file)
	# Get the topic name
	user_input=config['TOPIC']['topic']
	print("Tweetsfilter : ", config['TOPIC']['topic'])
	if user_input !="":
		word = user_input 
		print(word)
	else:
		word="Bitcoin"
		print(word)
	# Get auhentification to log into the Twitter API from the config files
	consumer_key = config['AUTH']['consumer_key']
	consumer_secret =config['AUTH']['consumer_secret']
	access_token = config['AUTH']['access_token']
	access_secret = config['AUTH']['access_secret']
	
	#Authentification with OAuthHandler
	auth = OAuthHandler(consumer_key, consumer_secret)
	auth.set_access_token(access_token, access_secret)
	
	#Listen to Twitter-Stream
	twitter_stream = Stream(auth, TweetListener())
	#Filter to the search word (e.g. Bitcoin) and sorting for english messages
	twitter_stream.filter(languages=['en'], track=[word])