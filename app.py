
import json
import os
import re
import sqlite3

from flask import Flask, request
import twitter


app = Flask(__name__)
PATH = os.path.dirname(os.path.realpath(__file__))
TEST_MODE = False

# Match UUID4
UUID_PATT = re.compile(r'^[a-z0-9]{8}-([a-z0-9]{4}-){3}[a-z0-9]{12}$')

with open(PATH + '/web_config.json') as f:
    web_config = json.load(f)


def db_connect():
    conn = sqlite3.connect(web_config['sqlite'])
    c = conn.cursor()
    return c, conn


@app.route('/posttweet')
def post_tweet():
    
    tweet_uid = request.args.get('uid')

    if not tweet_uid or not bool(UUID_PATT.match(tweet_uid)):
        return app.response_class(
            response='{"error":"invalid request"}',
            status=400,
            mimetype='application/json'
        )
    

    # get tweet from database
    c, conn = db_connect()
    try:
        c.execute('SELECT full_text, original_tweet_uid from tweets where uid=?', (tweet_uid,))
        full_text, original_tweet_id = c.fetchall()[0]
        c.execute('DELETE FROM tweets WHERE original_tweet_uid=?', (original_tweet_id,))
        conn.commit()
    except Exception as e:
        print(e)
        return app.response_class(
            response='{"error":"server error"}',
            status=500,
            mimetype='application/json')
    finally:
        c.close()
        conn.close()


    # Post to twitter
    with open(PATH+'/creds.json') as f:
        creds = json.load(f)
    api = twitter.Api(**creds)
    if not TEST_MODE:
        api.PostUpdate(status=full_text)
    else:
        print("TEST MODE: posting", repr(full_text))


    return app.response_class(
            response='{"ok":"'+full_text+'"}',
            status=200,
            mimetype='application/json'
        )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=web_config['port'])