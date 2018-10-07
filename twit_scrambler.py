
from copy import deepcopy
import datetime as dt
import http.client, urllib
import json
import os
import random
import re
import time
from uuid import uuid4

import nltk
nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')

import twitter

TEST_MODE = False


PATH = os.path.dirname(os.path.realpath(__file__))
URL_PATT = re.compile(r'http(s)?:\/\/(\w|\.|\/|\?)+')
DATA_FILE_NAMING_CONV = PATH + '/%s_data.txt'
DEFAULT_LOOKBACK = 14
DEFAULT_TWEETS_TO_MIX = 10
MIN_WORDS = 10
MIN_SWAP_WORD_LEN = 4
MIN_SWAPS_TO_MAKE = 2
TWEETS_TO_PULL = 100
TWEET_CHAR_LIMIT = 279
TWT_FIELDS = 'full_text'
WORD = 0
WTYPE = 1
TARGET_TWEET_OVERRIDE = None
MIN_SWAP_PERCENT = 0.15
TWEET_ITERATIONS = 3


# Set the twitter accounts to pull tweets from.
with open(PATH+'/twitter_accounts.json') as f:
    TWITTER_ACCOUNTS = json.load(f)


TYPES_TOSWAP = (
    'VB',   # Verbs
    'VBG',  # Verbs ending in 'ING'
    'NN',   # Nouns
    'NNS',  # Plural Nouns
    'NNP',  # Proper Nouns
    'NNPS', # Proper plural Nouns
    'JJ',   # Adjective
)

SWAP_BLACK_LIST = (
    '@', 'of', 'in', 'at', 't', 'doesn', 'can', '-', ':', '?', '[', ']', '{', '}',
    'be', 'do', ',', '.', '"', '\'', '`', 'great'
)

HTML_SWAPS = {
      '&gt;': '>',
      '&lt;': '<',
      '&apos;': "'",
      '&quot;': '"',
      '&amp;': '&'
}


def init_db(c, conn):
    sql = '''CREATE TABLE IF NOT EXISTS "tweets" (
                `uid`	TEXT NOT NULL,
                `original_tweet_uid`	TEXT NOT NULL,
                `full_text`	TEXT NOT NULL,
                PRIMARY KEY(uid)
            )'''
    c.execute(sql)
    conn.commit()


def send_alert(message, uid):
    if not pushover_creds:
        return
    print('sending alert:', message)
    conn = http.client.HTTPSConnection("api.pushover.net:443")

    print('TEST_MODE', TEST_MODE)

    url = (web_config['test_host'] if TEST_MODE else web_config['host']) +"/posttweet?uid="+uid

    print(conn.request("POST", "/1/messages.json",
        urllib.parse.urlencode({
            "token":pushover_creds['application_key'],
            "user":pushover_creds['user_key'],
            "message": message,
            "url":url,
            "url_title":"post to twitter"
        }), { "Content-type": "application/x-www-form-urlencoded" }))


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
        ('judge', 'kavanaugh', 'Judge Kavanaugh', 'NNP'),
        ('mike', 'pense', 'Mike Pense', 'NNP'),
        ('jeff', 'sessions', 'Jeff Sessions', 'NNP'),
        ('donald', 'trump', 'Donald Trump', 'NNP'),
        ('west', 'virginia', 'West Virginia', 'NNP'),
        ('north', 'carolina', 'North Carolina', 'NNP'),
        ('south', 'carolina', 'South Carolina', 'NNP'),
        ('new', 'york', 'New York', 'NNP'),
        ('new', 'jersey', 'New Jersey', 'NNP'),
        ('new', 'mexico', 'New Mexico', 'NNP'),
        ('nancy', 'pelosi', 'Nancy Pelosi', 'NNP'),
        ('bob', 'meuller', 'Bob Meuller', 'NNP'),
        ('robert', 'meuller', 'Robert Meuller', 'NNP'),
    ]

    words = [w[WORD] for w in word_array]
    cleaned_words = [w[WORD].lower().replace(' ', '') for w in word_array]
    
    for fixes in forced_pairs:
        if all(w in cleaned_words for w in fixes[:-2]):

            # make sure the fix words are next to each other
            # https://stackoverflow.com/questions/33575235/python-how-to-see-if-the-list-contains-consecutive-numbers
            ixs = [cleaned_words.index(w) for w in fixes[:-2]]
            if sorted(ixs) != list(range(min(ixs), max(ixs)+1)):
                print(ixs, 'not consecutive skipping fix!')
                continue

            print("FIXING", fixes)
            ix = cleaned_words.index(fixes[0])
            word_array = [tup for tup in word_array if tup[WORD].lower() not in fixes[:-2]]
            word_array.insert(ix, tuple(fixes[-2:]))
    
    return word_array


def build_mashed_tweet(target_tweet, mix, twit):
    # given a tweet and a mixed bag of words, mash up the tweet
    target_tweet_parts = clean_word_array(nltk.pos_tag(nltk.word_tokenize(target_tweet)))
    print(target_tweet_parts)
    
    # create mashup_map of {word_type: available_worlds[]}
    mix_tweet_parts = []
    for twt in mix:
        mix_tweet_parts += clean_word_array(nltk.pos_tag(nltk.word_tokenize(twt)))
    mashup_map = {}
    mix_tweet_parts = [word for word in mix_tweet_parts if not word[WORD].endswith('..')]

    for word in mix_tweet_parts:
        if word[WORD].lower() in SWAP_BLACK_LIST or len(word[WORD]) < MIN_SWAP_WORD_LEN:
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
                and random.random() <= twit['mix_perc']):
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
    
    mashed_tweet_str = ' '.join(mashed_tweet)
    mashed_tweet_str = mashed_tweet_str.replace(' , ', ', ')\
                                        .replace(' . ', '. ')\
                                        .replace(' ’ ', '’')\
                                        .replace(' \' ', '\'')\
                                        .replace(' !', '!')
    print('swaps_performed', swaps_performed)

    if swaps_performed < MIN_SWAPS_TO_MAKE:
        print("Not enough swaps performed (count), SKIPPING THIS TWEET", swaps_performed)
        return None
    
    if (swaps_performed / len(target_tweet_parts)) < MIN_SWAP_PERCENT:
        print("Not enough swaps performed (%), SKIPPING THIS TWEET", (swaps_performed / len(target_tweet_parts)))
        return None 
    
    # remove encoded HTML chars 
    for search, repl in HTML_SWAPS.items():
        if search in mashed_tweet_str:
            mashed_tweet_str = mashed_tweet_str.replace(search, repl)
    
    return twit.get('alias', twit['handle']) + ': ' + mashed_tweet_str


def main(twit, api):

    print('----------', twit['handle'], '-----------')

    # Download Tweets
    resp = api.GetUserTimeline(
        screen_name=twit['handle'],
        count=TWEETS_TO_PULL,
        include_rts=False,
        exclude_replies=True,
        trim_user=True
    )
    resp = [r.AsDict() for r in resp]
    print("got back", len(resp), "tweets")
    print("most recent tweet", repr(resp[0][TWT_FIELDS]))

    # Remove URLs, remove tweets that are too short
    for ix, twt in enumerate(resp):
        resp[ix][TWT_FIELDS] = URL_PATT.sub('', twt[TWT_FIELDS]).strip()
    resp = [r for r in resp if len(r[TWT_FIELDS].split(' ')) >= MIN_WORDS]

    print("most recent CLEANED tweet", repr(resp[0][TWT_FIELDS]))

    # Get tweet IDs we've already used
    try:
        with open(DATA_FILE_NAMING_CONV % twit['handle']) as f:
            used_tweets = f.read().split('\n')
    except IOError:
        used_tweets = []

    
    if not TEST_MODE and resp[0]['id_str'] in used_tweets:
        print("already used this tweet! BYE!")
        return
    else:
        print("\n NEW TWEET FOUND! -_- oh god \n")
    

    # Select a tweet to use (most recent)
    target_tweet = resp.pop(0) if not TEST_MODE else resp.pop(random.randint(0, len(resp)-1))
    print('using this tweet:\n', repr(target_tweet[TWT_FIELDS]))

    # Generate new tweets
    def truncate(string):
        if len(string) <= TWEET_CHAR_LIMIT:
            return string
        else:
            return string[0:TWEET_CHAR_LIMIT-2] + '..'

    op_tweet_uid = str(uuid4())
    print("op_tweet_uid", op_tweet_uid)
    new_tweets = []
    for i in range(TWEET_ITERATIONS):

        mix_tweet = []
        tweet_pool = deepcopy(resp)
        for i in range(twit['tweets_to_mix']):
            if len(tweet_pool) > 0:
                max_ix = len(tweet_pool)-1
                mix_tweet.append(tweet_pool.pop(random.randint(0, max_ix)))
            else:
                break
        
        if len(mix_tweet) < 1:
            print("mix_tweet is empty")
            return


        new_tweet = build_mashed_tweet(TARGET_TWEET_OVERRIDE or target_tweet[TWT_FIELDS], 
                                        [t[TWT_FIELDS] for t in mix_tweet], twit)
        if new_tweet:
            new_tweets.append({
                "full_text":truncate(new_tweet),
                "original_tweet_uid": op_tweet_uid,
                "uid":str(uuid4())
            })
    
    if len(new_tweets) < 1:
        print("No acceptable mashed tweets :/")
        return
    
    # send new tweets to database
    from app import db_connect
    c, conn = db_connect()
    try:
        init_db(c, conn)
        for t in new_tweets:
            c.execute('INSERT INTO tweets (uid, original_tweet_uid, full_text) VALUES (?,?,?)', (t['uid'], t['original_tweet_uid'], t['full_text']))
        conn.commit()
    except Exception as e:
        print("error inserting into DB", e)
        raise
    finally:
        c.close()
        conn.close()
    

    # send pushover alerts
    for t in new_tweets:
        send_alert(t['full_text'], t['uid'])
    

    # Update txt file with target tweet ID
    if not TEST_MODE:
        print("updating", DATA_FILE_NAMING_CONV % twit['handle'])
        used_tweets.insert(0, target_tweet['id_str'])
        used_tweets = used_tweets[0:500]
        with open(DATA_FILE_NAMING_CONV % twit['handle'], 'w') as f:
            for tid in used_tweets:
                if tid:
                    f.write(tid+'\n')
    



if __name__ == '__main__':
    
    # Twitter Creds
    with open(PATH+'/creds.json') as f:
        creds = json.load(f)

    # Pushover Creds
    with open(PATH+'/pushover_creds.json') as f:
        pushover_creds = json.load(f)

    # Flask Config
    with open(PATH+'/web_config.json') as f:
        web_config = json.load(f)

    
    # Construct API wrapper and authenticate
    creds['tweet_mode'] = 'extended'
    api = twitter.Api(**creds)
    if not api.VerifyCredentials():
        raise Exception("Could not verify twitter api credentials")

    for twit in TWITTER_ACCOUNTS:
        try:
            main(twit, api)
        except Exception as e:
            send_alert('ERROR'+str(e), 'nouid')
        time.sleep(2)