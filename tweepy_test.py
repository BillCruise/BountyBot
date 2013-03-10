# Test sending a Tweet.

import tweepy
import ConfigParser

from tweepy import *
from time import ctime, gmtime, mktime, strftime

def main():
    try:
        tweet('Test status sent from tweepy.')
    except TweepError as te:
        print te.message
        log('test.log', te.message)

# Update the Twitter account authorized 
# in settings.cfg with a status message.
def tweet(status):
    config = ConfigParser.RawConfigParser()
    config.read('settings.cfg')
    
    # http://dev.twitter.com/apps/myappid
    CONSUMER_KEY = config.get('Twitter OAuth', 'CONSUMER_KEY')
    CONSUMER_SECRET = config.get('Twitter OAuth', 'CONSUMER_SECRET')
    # http://dev.twitter.com/apps/myappid/my_token
    ACCESS_TOKEN_KEY = config.get('Twitter OAuth', 'ACCESS_TOKEN_KEY')
    ACCESS_TOKEN_SECRET = config.get('Twitter OAuth', 'ACCESS_TOKEN_SECRET')

    auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_TOKEN_KEY, ACCESS_TOKEN_SECRET)
    api = tweepy.API(auth)
    result = api.update_status(status)
    

def log(filename, message):
    timestamp = strftime("%Y %b %d %H:%M:%S UTC: ", gmtime())
    with open (filename, 'a') as f:
        f.write (timestamp + message + '\n')

    
if __name__ == '__main__':
    main()
