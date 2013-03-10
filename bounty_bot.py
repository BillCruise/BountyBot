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

import json
import sys
import tweepy
import ConfigParser
import HTMLParser

from tweepy import *
from ConfigParser import NoSectionError, NoOptionError
from time import ctime, gmtime, mktime, strftime
from urllib2 import urlopen, URLError
from zlib import decompress, MAX_WBITS

def main():
    # Get the time now and 8 hours ago.
    to_time = int(mktime(gmtime()))
    print 'Time Now:', ctime(to_time)
    from_time = to_time - (8 * 60 * 60)

    # Add 7 days to those times for bounty expiration comparison.
    # Unfortunately bounty sort orders are not based on the time the bounty
    # was posted or expires, but on the time the question was posted.
    from_time += (7 * 24 * 60 * 60)
    to_time += (7 * 24 * 60 * 60)

    print 'Expiration target window:'
    print ctime(from_time)
    print ctime(to_time)
    print
    window_msg = 'Target Window: ' + ctime(from_time) + ' to ' + ctime(to_time)
    log('status.log', window_msg)

    try:
        recent_bounties = request_bounties(from_time, to_time)
        
        max_bounty = find_max(recent_bounties)
        
        print '** Maximum Bounty **'
        display(max_bounty)

        status = format_status_msg(max_bounty)
        
        print status
        log('status.log', status)

        closes_msg = 'Bounty Closes: ' + ctime(max_bounty['bounty_closes_date'])
        log('status.log', closes_msg)
        
        tweet(status)

    except TweepError as te:
        print te.message
        log('error.log', te.message)
    except URLError:
        print 'URL error requesting bounties.'
        log('error.log', 'URL error requesting bounties.')
    except:
        print 'Unexpected error:', sys.exc_info()[0]
        log('error.log', 'Unexpected error: ' + str(sys.exc_info()[0]))


# Get a list of new bounty questions from Stack Overflow.
def request_bounties(from_time, to_time):
    config = ConfigParser.RawConfigParser()
    config.read('settings.cfg')
    se_oauth_key = None

    try:
        se_oauth_key = CONSUMER_KEY = config.get('Stack Exchange OAuth', 'KEY')
    except (NoSectionError, NoOptionError) as e:
        pass
    
    print 'SE OAuth Key:', se_oauth_key
    
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
        json_data = decompress(raw_data, 16 + MAX_WBITS).decode('UTF-8')
        data = json.loads(json_data)
    
        bounties = data['items']
        has_more = data['has_more']
    
        for bounty in bounties:
            close = bounty['bounty_closes_date']
            if from_time < close and close < to_time:
                recent_bounties.append(bounty)
                print 'Bounty:', count
                display(bounty)
                count += 1

        page += 1

    return recent_bounties


# Display the contents of a JSON bounty string.
def display(bounty):
    print bounty['title']
    print 'Tags:', bounty['tags']
    print 'Bounty Amount:', bounty['bounty_amount']
    print 'Question Score:', bounty['score']
    print 'Bounty Closes:', ctime(bounty['bounty_closes_date'])
    print 'View Count:', bounty['view_count']
    print 'Question Id:', bounty['question_id']
    print 'Is Answered:', bounty['is_answered']
    print


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
    bounty_link += str(bounty_json['question_id']) + '/1288'

    details = 'Amt:' + str(bounty_json['bounty_amount'])
    tags = bounty_json['tags']
    tag = hashify(tags[0])
    details += ' ' + tag

    # The URL in the status message will be shortened to
    # 22 characters (24 with surrounding spaces)
    # https://dev.twitter.com/blog/upcoming-tco-changes
    msg_length = len(bounty_title) + 24 + len(details)

    # Truncate the title to fit in a 140 character status message
    if msg_length > 140:
        allowed_title_len = 140 - (24 + len(details))
        bounty_title = bounty_title[0:allowed_title_len-3]
        bounty_title = bounty_title.rpartition(' ')[0] + '...'

    status = bounty_title + ' ' + bounty_link + ' ' + details

    # Add more tags if they'll fit in the 140-character limit
    tag_index = 1
    while tag_index < len(tags):
        tag = hashify(tags[tag_index])
        if (len(status) + len(tag) + 1) < 140:
            status += (' ' + tag)
        tag_index += 1
    
    return status
    

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
    if tag == 'c++':
        tag = 'cpp'
    elif tag == 'c#':
        tag = 'csharp'
    elif tag == 'f#':
        tag = 'fsharp'
    elif tag == 'asp.net':
        tag = 'ASPdotNET'
    elif tag == '.net':
        tag = 'dotNET'
    elif tag == 'objective-c':
        tag = 'ObjectiveC'
    elif tag == 'ruby-on-rails':
        tag = 'RubyOnRails'
    elif tag == 'ruby-on-rails-3':
        tag = 'RubyOnRails3'
    elif tag == 'sql-server':
        tag = 'SQLServer'
    elif tag == 'sql-server-2005':
        tag = 'SQLServer2005'
    elif tag == 'sql-server-2008':
        tag = 'SQLServer2008'
    elif tag == 'asp.net-mvc':
        tag = 'ASPdotNetMVC'
    elif tag == 'asp.net-mvc-3':
        tag = 'ASPdotNetMVC3'
    elif tag == 'vb.net':
        tag = 'VBdotNET'
    elif tag == 'visual-studio':
        tag = 'VisualStudio'
    elif tag == 'visual-studio-2010':
        tag = 'VS2010'
    elif tag == 'web-services':
        tag = 'webservices'
    elif tag == 'actionscript-3':
        tag = 'ActionScript3'
    elif tag == 'cocoa-touch':
        tag = 'CocoaTouch'
    elif tag == 'entity-framework':
        tag = 'EntityFramework'
    elif tag == 'jquery-ui':
        tag = 'jqueryUI'
    elif tag == 'node.js':
        tag = 'NodeJS'
    elif tag == 'internet-explorer':
        tag = 'IE'
    elif tag == '.htaccess':
        tag = 'htaccess'
    elif tag == 'unit-testing':
        tag = 'UnitTesting'
    elif tag == 'google-app-engine':
        tag = 'GAE'
    elif tag == 'windows-phone-7':
        tag = 'WindowsPhone7'
    elif tag == 'google-maps':
        tag = 'GoogleMaps'

    return '#' + tag


# Write a timestamped message to the specified log file.
def log(filename, message):
    timestamp = strftime("%Y %b %d %H:%M:%S UTC: ", gmtime())
    with open (filename, 'a') as f:
        f.write (timestamp + message + '\n')


if __name__ == '__main__':
    main()
