FROM python:latest

ADD TweetProducer.py .
ADD config.ini .

RUN pip install requests tweepy
RUN pip install requests pykafka
RUN pip install requests configparser
ENTRYPOINT [ "python","./TweetProducer.py" ] 

