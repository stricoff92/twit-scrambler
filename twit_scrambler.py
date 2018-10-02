
import datetime as dt
import json
import os
import random
import re

import nltk
nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')

import twitter


PATH = os.path.dirname(os.path.realpath(__file__))
URL_PATT = re.compile(r'http(s)?:\/\/(\w|\.|\/|\?)+')
DATA_FILE_NAMING_CONV = PATH + '/%s_data.txt'
DEFAULT_LOOKBACK = 14
DEFAULT_TWEETS_TO_MIX = 5
MIN_WORDS = 10


# Set the twitter accounts to pull tweets from.
TWITTER_ACCOUNTS = [
    {'handle':'realDonaldTrump', 'lookback':14, 'tweets_to_mix':5}
]


def main(twit, api):

    # Build Query String
    qs = "q=from%3A{0}&result_type=recent&since={1}&count=100".format(
        twit['handle'],
        (dt.date.today()-dt.timedelta(days=twit.get('lookback', DEFAULT_LOOKBACK))).strftime('%Y-%m-%d')
    )

    # Download Tweets
    results = [r.AsDict() for r in api.GetSearch(raw_query=qs)]

    # clean tweets (they're filthy)
    for ix, twt in enumerate(results):
        results[ix]['text'] = URL_PATT.sub('', twt['text'])
    results = [r for r in results if len(r['text'].split(' ')) >= MIN_WORDS]

    # Get tweet IDs we've already used
    try:
        with open(DATA_FILE_NAMING_CONV % twit['handle']) as f:
            used_tweets = f.read().split('\n')
    except IOError:
        used_tweets = []
    

    # Remove Tweets we've already used
    new_results = [r for r in results if r['id_str'] not in used_tweets]
    if len(new_results) == 0:
        print("no new tweets")
        return


    # Select a tweet to use (most recent)
    target_tweet = new_results.pop(0)

    # Select older tweets to mix in with new tweet
    results = [r for r in results if r['id_str'] != target_tweet['id_str']]
    mix_tweet = random.choices(results, k=twit.get('tweets_to_mix', DEFAULT_TWEETS_TO_MIX))

    print('using this tweet:\n', target_tweet['text'])
    print('\ntweets to mix in:', '\n'.join(r['text'] for r in mix_tweet))

    



if __name__ == '__main__':
    
    

    with open(PATH+'/creds.json') as f:
        creds = json.load(f)

    api = twitter.Api(consumer_key=creds['consumer_key'],
                        consumer_secret=creds['consumer_secret'],
                        access_token_key=creds['access_token_key'],
                        access_token_secret=creds['access_token_secret'])
    if not api.VerifyCredentials():
        raise Exception("Could not verify twitter api credentials")

    for twit in TWITTER_ACCOUNTS:
        main(twit, api)