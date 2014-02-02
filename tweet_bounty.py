import webapp2
import logging

import json
import sys
import tweepy
import calendar
import ConfigParser
import HTMLParser

from tweepy import *
from ConfigParser import NoSectionError, NoOptionError
from time import gmtime, strftime
from urllib2 import urlopen, URLError
from zlib import decompress, MAX_WBITS

HOURS = 8
USER_ID = 1288 # Your Stack Overflow user id for sharing links
MAX_TWEET_LEN = 140
DATE_FORMAT = "%Y %b %d %H:%M:%S UTC"


# Downloads 'featured' (bountied) questions from Stack Overflow, picks the
# most interesting one based on the amount of the bounty and the score of
# the question, then posts a link to the question on Twitter.
#
# Author: Bill Cruise
#        (Bill the Lizard on Stack Overflow, @lizardbill on Twitter)
#
# Dependencies: tweepy (https://github.com/tweepy/tweepy)
#               Stack Exchange API: https://api.stackexchange.com/docs
#               Twitter API: https://dev.twitter.com/
class TweetBounty(webapp2.RequestHandler):
    def get(self):
        # Get UTC time now and 8 hours ago.
        to_time = calendar.timegm(gmtime())
        self.response.write('Time Now: ' + strftime(DATE_FORMAT, gmtime(to_time)) + '<br/>')
        from_time = to_time - (HOURS * 60 * 60)

        # Add 7 days to those times for bounty expiration comparison.
        # Unfortunately bounty sort orders are not based on the time the bounty
        # was posted or expires, but on the time the question was posted.
        from_time += (7 * 24 * 60 * 60)
        to_time += (7 * 24 * 60 * 60)

        from_time_displ = strftime(DATE_FORMAT, gmtime(from_time))
        to_time_displ = strftime(DATE_FORMAT, gmtime(to_time))
        window_msg = 'Expiration Target Window: ' + from_time_displ + ' to ' + to_time_displ
        logging.info(window_msg)
        self.response.write(window_msg + '<br/>')
        self.response.write('<br/>')

        try:
            recent_bounties = self.request_bounties(from_time, to_time)
        
            max_bounty = find_max(recent_bounties)
        
            self.response.write('** Maximum Bounty **<br/>')
            self.display(max_bounty)

            status = format_status_msg(max_bounty)
        
            self.response.write(status)
            logging.info(status)

            close_time = gmtime(max_bounty['bounty_closes_date'])
            close_time_fmt = strftime(DATE_FORMAT, close_time)
            closes_msg = 'Bounty Closes: ' + close_time_fmt
            logging.info(closes_msg)
        
            tweet(status)

        except TweepError:
            logging.error('TweepError: ' + str(sys.exc_info()[0]) + str(sys.exc_info()[1]))
            logging.error(status)
        except URLError:
            logging.error('URLError: ' + str(sys.exc_info()[0]) + str(sys.exc_info()[1]))
            logging.error(status)
        except:
            logging.error('Unexpected error: ' + str(sys.exc_info()[0]) + str(sys.exc_info()[1]))
            

    # Display the contents of a JSON bounty string.
    def display(self, bounty):
        self.response.write(bounty['title'] + '<br/>')
        self.response.write('Tags: ' + str(bounty['tags']) + '<br/>')
        self.response.write('Bounty Amount: ' + str(bounty['bounty_amount']) + '<br/>')
        self.response.write('Question Score: ' + str(bounty['score']) + '<br/>')
        close_time = gmtime(bounty['bounty_closes_date'])
        close_time_fmt = strftime(DATE_FORMAT, close_time)
        self.response.write('Bounty Closes: ' + close_time_fmt + '<br/>')
        self.response.write('View Count: ' + str(bounty['view_count']) + '<br/>')
        self.response.write('Question Id: ' + str(bounty['question_id']) + '<br/>')
        self.response.write('Is Answered: ' + str(bounty['is_answered']) + '<br/>')
        self.response.write('<br/>')


    # Get a list of new bounty questions from Stack Overflow.
    def request_bounties(self, from_time, to_time):
        config = ConfigParser.RawConfigParser()
        config.read('settings.cfg')
        se_oauth_key = None

        try:
            se_oauth_key = CONSUMER_KEY = config.get('Stack Exchange OAuth', 'KEY')
        except (NoSectionError, NoOptionError) as e:
            pass
    
        page = 1
        page_size = 100
        has_more = True
        count = 1
        recent_bounties = []

        while(has_more):
            request = 'https://api.stackexchange.com/2.1/questions/featured'
            request += '?page=' + str(page) + '&pagesize=100'
            request += '&order=asc&sort=activity&site=stackoverflow'
            if se_oauth_key != None:
                request += '&key=' + se_oauth_key
    
            response = urlopen(request)
            raw_data = response.read()
            data = json.loads(raw_data)
    
            bounties = data['items']
            has_more = data['has_more']
    
            for bounty in bounties:
                close = bounty['bounty_closes_date']
                if from_time < close and close < to_time:
                    recent_bounties.append(bounty)
                    self.display(bounty)
                    count += 1

            page += 1

        return recent_bounties
    

# Find the maximum bounty.
# Give preference to highest scoring question in case of bounty ties.
def find_max(bounties):
    max_bounty = ''
    max_bounty_amt = 0
    max_bounty_score = 0
    
    for bounty in bounties:
        if bounty['bounty_amount'] > max_bounty_amt:
            max_bounty = bounty
            max_bounty_amt = bounty['bounty_amount']
            max_bounty_score = bounty['score']
        elif bounty['bounty_amount'] == max_bounty_amt:
            if bounty['score'] > max_bounty_score:
                max_bounty = bounty
                max_bounty_amt = bounty['bounty_amount']
                max_bounty_score = bounty['score']
            
    return max_bounty
    

# Format a JSON bounty string into a 140-character status message.
def format_status_msg(bounty_json):
    bounty_title = bounty_json['title']
    h = HTMLParser.HTMLParser()
    bounty_title = h.unescape(bounty_title)
    
    bounty_link = 'http://stackoverflow.com/q/'
    bounty_link += str(bounty_json['question_id']) + '/' + str(USER_ID)

    details = 'Amt:' + str(bounty_json['bounty_amount'])
    tags = bounty_json['tags']
    tag = hashify(tags[0])
    details += ' ' + tag

    # The URL in the status message will be shortened to
    # 22 characters (24 with surrounding spaces)
    # https://dev.twitter.com/blog/upcoming-tco-changes
    msg_length = len(bounty_title) + 24 + len(details)

    # Truncate the title to fit in a 140 character status message
    if msg_length > MAX_TWEET_LEN:
        allowed_title_len = MAX_TWEET_LEN - (24 + len(details))
        bounty_title = bounty_title[0:allowed_title_len-3]
        bounty_title = bounty_title.rpartition(' ')[0] + '...'

    status = bounty_title + ' ' + bounty_link + ' ' + details

    # Add more tags if they'll fit in the 140-character limit
    tag_index = 1
    while tag_index < len(tags):
        tag = hashify(tags[tag_index])
        if (len(status) + len(tag) + 1) < MAX_TWEET_LEN:
            status += (' ' + tag)
        tag_index += 1
    
    return status

# Tweet the number of bounties, total bounty amount, and top tags for the week.
class TweetBountyStats(webapp2.RequestHandler):
    def get(self):
        try:
            bounty_count, bounty_total, tag_counts, tag_bounty_totals = self.request_stats()
            
            self.display_stats(bounty_count, bounty_total)

            status = 'Bounties posted this week: ' + str(bounty_count) + '\n'
            status += 'Total amount of bounties posted: ' + str(bounty_total) + '\n'
            status += 'Average bounty: ' + str(bounty_total / bounty_count)
            tweet(status)

            # The two sorts below return lists of (key,value) tuples sorted by values.
            key, val = 0, 1

            # Sort tags by number of bounties
            s_tag_counts = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
            # Sort tags by total amount bountied
            s_tag_bounty_totals = sorted(tag_bounty_totals.items(), key=lambda x: x[1], reverse=True)

            self.display_top_tags(s_tag_counts, s_tag_bounty_totals)

            # Compose status messages and tweet
            status = 'Top tags by number of bounties:\n'
            status += hashify(s_tag_counts[0][key]) + ': ' + str(s_tag_counts[0][val]) + '\n'
            status += hashify(s_tag_counts[1][key]) + ': ' + str(s_tag_counts[1][val]) + '\n'
            status += hashify(s_tag_counts[2][key]) + ': ' + str(s_tag_counts[2][val])
            tweet(status)
            
            status = 'Top tags by bounty amount:\n'
            status += hashify(s_tag_bounty_totals[0][key]) + ': ' + str(s_tag_bounty_totals[0][val]) + '\n'
            status += hashify(s_tag_bounty_totals[1][key]) + ': ' + str(s_tag_bounty_totals[1][val]) + '\n'
            status += hashify(s_tag_bounty_totals[2][key]) + ': ' + str(s_tag_bounty_totals[2][val])
            tweet(status)

        except TweepError:
            logging.error('TweepError: ' + str(sys.exc_info()[0]) + str(sys.exc_info()[1]))
            logging.error(status)
        except URLError:
            logging.error('URLError: ' + str(sys.exc_info()[0]) + str(sys.exc_info()[1]))
            logging.error(status)
        except:
            logging.error('Unexpected error: ' + str(sys.exc_info()[0]) + str(sys.exc_info()[1]))

    # Get a stats for all bounty questions from Stack Overflow.
    # Stats returned are total number of bounties, count and
    # total bounty for each tag.
    def request_stats(self):
        config = ConfigParser.RawConfigParser()
        config.read('settings.cfg')
        se_oauth_key = None

        try:
            se_oauth_key = CONSUMER_KEY = config.get('Stack Exchange OAuth', 'KEY')
        except (NoSectionError, NoOptionError) as e:
            pass
    
        page = 1
        page_size = 100
        has_more = True

        bounty_count = 0
        bounty_total = 0
        tag_counts = {}
        tag_bounty_totals = {}

        while(has_more):
            request = 'https://api.stackexchange.com/2.1/questions/featured'
            request += '?page=' + str(page) + '&pagesize=100'
            request += '&order=asc&sort=activity&site=stackoverflow'
            if se_oauth_key != None:
                request += '&key=' + se_oauth_key
    
            response = urlopen(request)
            raw_data = response.read()
            data = json.loads(raw_data)
    
            bounties = data['items']
            has_more = data['has_more']
    
            for bounty in bounties:
                bounty_count += 1
                bounty_total += bounty['bounty_amount']
                tags = bounty['tags']
                for tag in tags:
                    if tag in tag_counts:
                        tag_counts[tag] += 1
                        tag_bounty_totals[tag] += bounty['bounty_amount']
                    else:
                        tag_counts[tag] = 1
                        tag_bounty_totals[tag] = bounty['bounty_amount']
            page += 1

        return bounty_count, bounty_total, tag_counts, tag_bounty_totals

    # Display the number of bounties posted, total amount, and average bounty
    def display_stats(self, bounty_count, bounty_total):
        self.response.write('Bounties posted this week: ')
        self.response.write(str(bounty_count) + '<br/>')

        self.response.write('Total amount of bounties posted: ')
        self.response.write(str(bounty_total) + '<br/>')

        self.response.write('Average bounty: ')
        self.response.write(str(bounty_total / bounty_count) + '<br/><br/>')

    # Display the top tags sorted by number of bounties and total bounty amount
    def display_top_tags(self, s_tag_counts, s_tag_bounty_totals):
        key, val = 0, 1
        
        self.response.write('Top tags by number of bounties: <br/>')
        for tag in range(0, 3):
            self.response.write(s_tag_counts[tag][key] + ': ' + str(s_tag_counts[tag][val]) + '<br/>')

        self.response.write('<br/>Top tags by bounty amount: <br/>')
        for tag in range(0, 3):
            self.response.write(s_tag_bounty_totals[tag][key] + ': ' + str(s_tag_bounty_totals[tag][val]) + '<br/>')


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


# Converts a Stack Overflow tag to a Twitter hashtag.
# The most common tags with special characters are covered,
# with special cases added as needed. (consider retagging on SO)
def hashify(tag):
    tag_dict = {'c++':'cpp', 'c#':'csharp', 'f#':'fsharp',
                'asp.net':'ASPdotNET', '.net':'dotNET',
                'objective-c':'ObjectiveC', 'xml-parsing':'XMLparsing',
                'ruby-on-rails':'RubyOnRails', 'ruby-on-rails-3':'RubyOnRails3',
                'sql-server':'SQLServer', 'sql-server-2005':'SQLServer2005',
                'sql-server-2008':'SQLServer2008',
                'asp.net-mvc':'ASPdotNetMVC', 'asp.net-mvc-3':'ASPdotNetMVC3',
                'vb.net':'VBdotNET', 'visual-studio':'VisualStudio',
                'visual-studio-2010':'VS2010',
                'web-services':'webservices', 'ActionScript3':'ActionScript3',
                'cocoa-touch':'CocoaTouch', 'entity-framework':'EntityFramework',
                'jquery-ui':'jqueryUI', 'node.js':'NodeJS',
                'internet-explorer':'IE', '.htaccess':'htaccess',
                'unit-testing':'UnitTesting', 'windows-phone-7':'WindowsPhone7',
                'google-maps':'GoogleMaps', 'android-layout':'androidlayout'
                }
    tag = tag_dict.get(tag, tag) # returns either mapping or the original tag
    return '#' + tag



app = webapp2.WSGIApplication([
    ('/tweet_bounty', TweetBounty),
    ('/tweet_bounty_stats', TweetBountyStats)
], debug=False)
