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

import logging
import cmd
import mitterlib.ui.console_utils as console_utils
import mitterlib.constants
import datetime

namespace = 'cmd'
threads = 1 # So no threads


def options(parser):
    # no options for this interface
    return


class Interface(cmd.Cmd):
    """The command line interface for Mitter."""

    # -----------------------------------------------------------------------
    # Methods required by cmd.Cmd (our commands)
    # -----------------------------------------------------------------------

    def do_timeline(self, line):
        """Return a list of new tweets in your friends timeline."""
        self._twitter.friends_timeline(self._show_tweets)
        return

    def do_replies(self, line):
        """Get a list of replies to you."""
        self._twitter.replies(self._show_tweets, watched_field='last_reply')
        return

    def do_update(self, line):
        """Update your status."""
        if len(line) > 160:
            # Twitter refuses such messages (or so says their documentation)
            print 'Your message have more than 160 characters and it is ' \
                    'very likely Twitter'
            print 'will refuse it.'
            print '(You can try shortening your URLs before posting.)'
            print
            print 'Your status was NOT updated.'
            return

        if len(line) > 140:
            print 'Your message have more than 140 characters and ' \
                    'Twitter may truncate it.'
            print 'It would still be visible in the website.'
            print '(You may be still good if you are sending an URL.)'
            answer = raw_input('Do you want to continue [Y/n]? ')
            if answer.lower() == 'n':
                print 'Updated aborted.'
                return

        self._twitter.update(line, self._post_update)
        return

    def do_exit(self, line):
        """Quit the application."""
        self._log.debug('Exiting application')
        self._twitter.close()
        self._log.debug('Connection closed')
        return True

    def do_EOF(self, line):
        """Quit the application (it's the same as "exit"). You can also use
        Ctrl+D."""
        print       # Cmd doesn't add an empty line after the ^D
        return self.do_exit(None)

    def do_delete(self, line):
        """Delete a tweet. You must provide the number of the displayed
        tweet."""
        tweet_id = int(line)
        if tweet_id < 1 or tweet_id > len(self._tweets):
            print 'No such tweet.'
            return

        real_tweet_id = self._tweets[tweet_id - 1]
        self._twitter.tweet_destroy(real_tweet_id, self._post_delete)
        return

    def emptyline(self):
        """Called when the user doesn't call any command. Default is to repeat
        the last command; we are going to call timeline() again."""
        return self.do_timeline(None)

    def default(self, line):
        """Called when we receive an unknown command; default is error
        message, we are going to call update() instead."""
        return self.do_update(line)


    # -----------------------------------------------------------------------
    # Callback methods (called by the Twitter library)
    # -----------------------------------------------------------------------

    def _show_tweets(self, data, error, watched_field='last_tweet'):
        """Function called after we receive the list of tweets."""

        if error == 401:
            # authentication fail
            print 'Request authorization failed. Please, check your details:'
            console_utils.authorization(self._save, namespace, self._prefs,
                    self._username, self._password, self._https, self._twitter)

            # this is a little bit icky
            # (just call the same thing that called ths function)
            if watched_field == 'last_tweet':
                self._twitter.friends_timeline(self._show_tweets)
                return

        if error:
            print 'Sorry, couldn\'t download your friends timeline.'
            return

        last_seen_tweet = self._prefs[watched_field]

        self._tweets = console_utils.print_tweets(data, last_seen_tweet,
                show_numbers=True)
        if self._tweets:
            self._prefs[watched_field] = self._tweets[-1]
            self._save(self._username, self._password, self._https,
                    namespace, self._prefs)

        if watched_field == 'last_tweet':
            self._last_update = datetime.datetime.now()

        self._refresh_rate_limit()
        return

    def _post_update(self, data, error):
        """Function called after we update the status on Twitter."""

        if error:
            print 'Twitter returned an error during update. Your status ' \
                    'was NOT updated.'
        else:
            self._refresh_rate_limit()
            print 'Your status was updated.'
        return

    def _post_delete(self, data, error):
        """Function called after we delete a tweet."""
        if error:
            if error == 403:
                # Ok, we are *assuming* that, if you get a Forbidden
                # error, it means it's not your tweet.
                print "You can't delete this tweet."
                # TODO: we are using Logging.Error in the Twitter
                # object when we get this error. So the user will
                # see connection errors instead of this simple
                # message.
            else:
                print 'Error deleting tweet.'
        else:
            print 'Tweet deleted.'
        self._refresh_rate_limit()
        return

    def _refresh_rate_limit(self):
        """Request the rate limit and update the prompt for that."""
        self._twitter.rate_limit_status(self._post_refresh_rate_limit)
        return

    def _post_refresh_rate_limit(self, data, error):
        """Callback for the _refresh_rate_limit."""
        if error or not data:
            return

        self._rate_limit = int(data['remaining_hits'])
        self._update_prompt()

    def _update_prompt(self):
        """Update the command line prompt."""
        if self._last_update:
            update_text = self._last_update.strftime('%H:%M')
        else:
            update_text = 'Never'
        self.prompt = ('[%d] Last update: %s> ' %
            (self._rate_limit, update_text))
        return


    # -----------------------------------------------------------------------
    # Methods required by the main Mitter code
    # -----------------------------------------------------------------------

    def __init__(self, save_callback, username, password, https, connection, \
            prefs):
        """Class initialization."""

        cmd.Cmd.__init__(self)
        self._log = logging.getLogger('ui.cmd')
        self._rate_limit = None
        self._last_update = None
        self._twitter = connection
        self._save = save_callback
        self._username = username
        self._password = password
        self._https = https
        self._tweets = []

        self._prefs = {
            'last_reply': int(prefs.get('last_reply', 0)),
            'last_tweet': int(prefs.get('last_tweet', 0))}

        intro = ['Welcome %s to Mitter %s.' % (username,
            mitterlib.constants.version),
            '',
            'From here, you can type "help" to get a list of ' \
                'available commands.',
            'If you start a line without a proper command, Mitter ' \
                'will create a new tweet.',
            'And empty line will retrieve the latest updates from ' \
                'your friend timeline.',
            '',
            '']
        self.intro = '\n'.join(intro)
        self.prompt = 'Mitter> '

        return

    def __call__(self):
        """Make the object callable; that's the only requirement for
        Mitter."""
        if not self._username:
            console_utils.authorization(self._save, namespace, self._prefs,
                    connection=self._twitter)

        self.cmdloop()
        return
