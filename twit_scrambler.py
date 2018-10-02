
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
DEFAULT_TWEETS_TO_MIX = 8
MIN_WORDS = 10
TWEETS_TO_PULL = 50
TWT_FIELDS = 'full_text'
POST_TO_TWITTER = False
WORD = 0
WTYPE = 1


# Set the twitter accounts to pull tweets from.
TWITTER_ACCOUNTS = [
    {'handle':'realDonaldTrump', 'lookback':14, 'tweets_to_mix':5, 'mix_perc':0.45}
]

TYPES_TOSWAP = (
    'VB',   # Verbs
    'VBG',  # Verbs ending in 'ING'
    'NN',   # Nouns
    'NNS',  # Plural Nouns
    'NNP', # Proper Nouns
)

SWAP_BLACK_LIST = (
    '@', 'of', 'in', 'at', 't', 'doesn', 'can', '-', ':', '?', '[', '}',
    'be', 'do', ',', '.'
)

def skip_word(word):
    return (
        word in SWAP_BLACK_LIST
        or bool(re.match(r'^\d+$', word))
        or bool(re.match(r'^\d\d\:\d\d$', word))
    )


def build_mashed_tweet(target_tweet, mix, perc):
    # given a tweet and a mixed bag of words, mash up the tweet
    target_tweet_parts = nltk.pos_tag(nltk.word_tokenize(target_tweet))
    print(target_tweet_parts)
    
    # create mashup_map of {word_type: available_worlds[]}
    # {'NNP':['Avenatti', 'Putin'], ...}
    mix_tweet_parts = []
    for twt in mix:
        mix_tweet_parts += nltk.pos_tag(nltk.word_tokenize(twt))
    mashup_map = {}
    for word in mix_tweet_parts:
        if word[WORD].lower() in SWAP_BLACK_LIST:
            continue
        if word[WTYPE] in mashup_map and mashup_map[word[WTYPE]].count(word[WORD]) == 0:
            mashup_map[word[WTYPE]].append(word[WORD])
        else:
            mashup_map[word[WTYPE]] = [word[WORD]]
    print(mashup_map)
    
    # Create new Tweet.
    mashed_tweet = []
    for ix, word in enumerate(target_tweet_parts):
        if (ix and word[WTYPE] in TYPES_TOSWAP 
                and word[WTYPE] in mashup_map 
                and not skip_word(word[WORD])
                and random.random() <= perc):
            # Swap out this word
            mashed_tweet.append(random.choice(mashup_map[word[WTYPE]]))
            print('swaping "%s" with "%s"' % (word, mashed_tweet[-1]))
        else:
            print("skipping swap of", word)
            mashed_tweet.append(word[WORD])
    
    return ' '.join(mashed_tweet)

    


def main(twit, api):

    # Build Query String
    qs = "q=from%3A{0}&result_type=recent&since={1}&count={2}&tweet_mode=extended".format(
        twit['handle'],
        (dt.date.today()-dt.timedelta(days=twit.get('lookback', DEFAULT_LOOKBACK))).strftime('%Y-%m-%d'),
        TWEETS_TO_PULL
    )

    # Download Tweets
    results = [r.AsDict() for r in api.GetSearch(raw_query=qs)]

    # clean tweets (they're filthy)
    for ix, twt in enumerate(results):
        results[ix][TWT_FIELDS] = URL_PATT.sub('', twt[TWT_FIELDS])
    results = [r for r in results if len(r[TWT_FIELDS].split(' ')) >= MIN_WORDS]

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

    print('using this tweet:\n', target_tweet[TWT_FIELDS])
    print('\ntweets to mix in:', '\n'.join(r[TWT_FIELDS] for r in mix_tweet))

    # Generate new tweet 
    new_tweet = build_mashed_tweet(target_tweet[TWT_FIELDS], [t[TWT_FIELDS] for t in mix_tweet], twit['mix_perc'])
    print('new mashed tweet\n', new_tweet)
    



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