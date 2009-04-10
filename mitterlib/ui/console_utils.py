#!/usr/bin/python
# -*- coding: utf-8 -*-

# Mitter, a Maemo client for Twitter.
# Copyright (C) 2007, 2008  Julio Biason, Deepak Sarda
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


def unhtml(text):
    """Convert text coming in HTML encoded to UTF-8 representations."""
    import re
    import htmlentitydefs

    new_text = []
    copy_pos = 0
    for code in re.finditer(r'&(\w+);', text):
        new_text.append(text[copy_pos:code.start()])
        entity = text[code.start()+1:code.end()-1]
        if entity in htmlentitydefs.name2codepoint:
            new_text.append(chr(htmlentitydefs.name2codepoint[entity]))
        else:
            new_text.append(code.group())
        copy_pos = code.end()

    new_text.append(text[copy_pos:])

    return u''.join(new_text)


def encode_print(text):
    """Try to print the text; if we get any UnicodeEncodeError, we print it
    without encoding."""
    try:
        print text
    except UnicodeEncodeError:
        import locale
        encoding = locale.getdefaultlocale()[1]
        if not encoding:
            encoding = 'ascii'
        print text.encode(encoding, 'replace')
        return


def print_tweets(data, highest_id, show_numbers=False):
    """Print the list of tweets."""
    # Twitter sends us the data from the newest to latest, which is not
    # good for displaying on a console. So we reverse the list.

    data.reverse()

    import datetime
    import textwrap
    timediff = datetime.datetime.utcnow() - datetime.datetime.now()

    count = 1
    tweets = []
    for tweet in data:
        id = int(tweet['id'])
        if id <= highest_id:
            # this is old tweet
            continue

        display_name = tweet['user']['name']
        created_at = tweet['created_at']
        message = tweet['text']
        username = tweet['user']['screen_name']

        display = textwrap.wrap(unhtml(message))
        display_date = created_at - timediff
        display_date = display_date.replace(microsecond = 0)

        if show_numbers:
            header = '%d. %s (%s) @ %s:' % (count, display_name, username,
                    str(display_date))
            count += 1
        else:
            header = '%s (%s) @ %s:' % (display_name, username,
                    str(display_date))
        encode_print(header)
        print '-' * len(header)

        for line in display:
            encode_print(line)
        print
        print

        tweets.append(id)

    return tweets


def authorization(save_callback, namespace, prefs, prev_username='',
        prev_password='', https=False, connection=None):
    """Request the user to type his credentials."""

    import getpass

    username = raw_input('Username [%s]: ' % (prev_username))
    password = getpass.getpass('Password [%s]: ' % (prev_password))

    if not username:
        username = prev_username

    if not password:
        password = prev_password

    save_callback(username, password, https, namespace, prefs)
    if connection:
        # update the connection information, or we'll try to connect again
        # with the wrong username/password.
        connection.username = username
        connection.password = password
    return
