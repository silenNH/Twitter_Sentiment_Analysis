import tweepy
from tweepy import OAuthHandler
from tweepy import Stream
from tweepy.streaming import StreamListener
import json
import pykafka
from configparser import ConfigParser
#python3 TweetReadProduceV4.py "Bitcoin"

class TweetListener(StreamListener):
	def __init__(self):
		self.client = pykafka.KafkaClient("broker:9092")
		self.producer = self.client.topics[bytes('twitter','ascii')].get_producer()

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
	config=ConfigParser()
	file='./config.ini'
	config.read(file)
	user_input=config['TOPIC']['topic']
	print("Tweetsfilter : ", config['TOPIC']['topic'])
	if user_input !="":
		word = user_input 
		print(word)
	else:
		word="Bitcoin"
		print(word)

	consumer_key = config['AUTH']['consumer_key']
	consumer_secret =config['AUTH']['consumer_secret']
	access_token = config['AUTH']['access_token']
	access_secret = config['AUTH']['access_secret']
	
	auth = OAuthHandler(consumer_key, consumer_secret)
	auth.set_access_token(access_token, access_secret)
	
	twitter_stream = Stream(auth, TweetListener())
	twitter_stream.filter(languages=['en'], track=[word])