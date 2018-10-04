
import datetime as dt
import http.client, urllib
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
DEFAULT_TWEETS_TO_MIX = 10
MIN_WORDS = 10
MIN_SWAP_WORD_LEN = 4
TWEETS_TO_PULL = 50
TWEET_CHAR_LIMIT = 279
TWT_FIELDS = 'full_text'
POST_TO_TWITTER = True
WORD = 0
WTYPE = 1
TARGET_TWEET_OVERRIDE = None #'The united states will build a wall betweet itself and Mexico. Mark my words!'


# Set the twitter accounts to pull tweets from.
TWITTER_ACCOUNTS = [
    {'handle':'realDonaldTrump', 'lookback':14, 'tweets_to_mix':10, 'mix_perc':0.5}
]

TYPES_TOSWAP = (
    'VB',   # Verbs
    'VBG',  # Verbs ending in 'ING'
    'NN',   # Nouns
    'NNS',  # Plural Nouns
    'NNP',  # Proper Nouns
    'JJ',   # Adjective
)

SWAP_BLACK_LIST = (
    '@', 'of', 'in', 'at', 't', 'doesn', 'can', '-', ':', '?', '[', ']', '{', '}',
    'be', 'do', ',', '.', '"', '\'', '`', 'great'
)


def skip_word(word):
    return (
        word.lower() in SWAP_BLACK_LIST
        or bool(re.match(r'^\d+$', word))
        or bool(re.match(r'^\d\d\:\d\d$', word))
    )


def clean_word_array(word_array):
    # NLTK isn't perfect. example: 'United States' gets broken up into 2 separate words but we'd like to
    # treat it like 1x Proper Noun.
    # Implement logic in this function to fix these errors.

    # 2nd to last element is the final string that should appear in the string
    # last element is the word type
    # elements 0 through length-3 are the strings to search for
    forced_pairs = [
        ('united', 'states', 'United States', 'NNP'),
        ('brett', 'kavanaugh', 'Brett Kavanaugh', 'NNP'),
        ('mike', 'pense', 'Mike Pense', 'NNP'),
        ('jeff', 'sessions', 'Jeff Sessions', 'NNP'),
        ('donald', 'trump', 'Donald Trump', 'NNP'),
        ('west', 'virginia', 'West Virginia', 'NNP'),
        ('north', 'carolina', 'North Carolina', 'NNP'),
        ('south', 'carolina', 'South Carolina', 'NNP'),
        ('new', 'york', 'New York', 'NNP'),
        ('new', 'jersey', 'New Jersey', 'NNP'),
        ('new', 'mexico', 'New Mexico', 'NNP'),
    ]

    words = [w[WORD] for w in word_array]
    cleaned_words = [w[WORD].lower().replace(' ', '') for w in word_array]
    
    for fixes in forced_pairs:
        if all(w in cleaned_words for w in fixes[:-2]):
            print("FIXING", fixes)
            ix = cleaned_words.index(fixes[0])
            word_array = [tup for tup in word_array if tup[WORD] not in fixes[:-2]]
            word_array.insert(ix, tuple(fixes[-2:]))
    
    return word_array



def build_mashed_tweet(target_tweet, mix, perc):
    # given a tweet and a mixed bag of words, mash up the tweet
    target_tweet_parts = clean_word_array(nltk.pos_tag(nltk.word_tokenize(target_tweet)))
    print(target_tweet_parts)
    
    # create mashup_map of {word_type: available_worlds[]}
    # {'NNP':['Avenatti', 'Putin'], ...}
    mix_tweet_parts = []
    for twt in mix:
        mix_tweet_parts += clean_word_array(nltk.pos_tag(nltk.word_tokenize(twt)))
    mashup_map = {}
    for word in mix_tweet_parts:
        if word[WORD].lower() in SWAP_BLACK_LIST or len(word[WORD]) <= MIN_SWAP_WORD_LEN:
            continue
        
        if word[WTYPE] in mashup_map and mashup_map[word[WTYPE]].count(word[WORD]) == 0:
            mashup_map[word[WTYPE]].append(word[WORD])
        elif word[WTYPE] not in mashup_map:
            mashup_map[word[WTYPE]] = [word[WORD]]
    
    print(mashup_map)
    
    # Create new Tweet
    mashed_tweet = []
    swaps_performed = 0
    for ix, word in enumerate(target_tweet_parts):
        if (ix and word[WTYPE] in TYPES_TOSWAP 
                and len(word[WORD]) >= MIN_SWAP_WORD_LEN
                and word[WTYPE] in mashup_map 
                and not skip_word(word[WORD])
                and random.random() <= perc):
            # Swap out this word
            if len(mashup_map[word[WTYPE]]):
                rand_word = mashup_map[word[WTYPE]].pop(random.randint(0, len(mashup_map[word[WTYPE]])-1))
                mashed_tweet.append(rand_word)
                swaps_performed += 1
                print('SWAPPING "%s" with "%s"' % (word, rand_word))
            else:
                print("skipping swap of", word)
                mashed_tweet.append(word[WORD])
        else:
            print("skipping swap of", word)
            mashed_tweet.append(word[WORD])
    
    mashed_tweet_str = '"' + ' '.join(mashed_tweet) +'"\n\n-'+twit['handle']+' (sort of)'
    mashed_tweet_str = mashed_tweet_str.replace(' , ', ', ')\
                                        .replace(' . ', '. ')\
                                        .replace(' ’ ', '’')\
                                        .replace(' \' ', '\'')\
                                        .replace(' !', '!')
    print('swaps_performed', swaps_performed)
    return mashed_tweet_str

    


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
    
    if results[0]['id_str'] in used_tweets:
        print("already used this tweet! BYE!")
        return
    

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
    new_tweet = build_mashed_tweet(TARGET_TWEET_OVERRIDE or target_tweet[TWT_FIELDS], 
                                    [t[TWT_FIELDS] for t in mix_tweet], twit['mix_perc'])
    print('new mashed tweet\n', new_tweet)


    # Post Tweet to Twitter
    def truncate(string):
        if len(string) <= TWEET_CHAR_LIMIT:
            return string
        else:
            return string[0:TWEET_CHAR_LIMIT-2] + '..'
    if POST_TO_TWITTER:
        api.PostUpdate(status=truncate(new_tweet))

        # Update txt file with target tweet ID
        used_tweets.insert(0, target_tweet['id_str'])
        used_tweets[0:500]
        with open(DATA_FILE_NAMING_CONV % twit['handle'], 'w') as f:
            for tid in used_tweets:
                f.write(tid+'\n')
    

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