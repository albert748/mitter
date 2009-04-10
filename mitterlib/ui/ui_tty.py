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

namespace = 'console'
threads = 1     # 1 will force the twitter lib to not use threads

import mitterlib.ui.console_utils as console_utils
import mitterlib
import logging

from optparse import OptionGroup


def options(parser):
    """Add command line options for this interface."""
    group = OptionGroup(parser, 'TTY interface')
    # I wonder how much confusion this will create.
    group.add_option('--updates',
        dest='updates',
        help='Display the latest updates',
        default=False,
        action='callback',
        callback=mitterlib.check_interfaces,
        callback_kwargs={'interface': 'tty', 'set': True})
    # this confustion between console and tty will kill me one day.
    # (Just to let you know: the 'inteface' value should be the same name
    #  used for the --interface option, even if the namespace is not it.)
    group.add_option('--update',
        dest='update',
        help='Update your status',
        default=None,
        type='str',
        metavar='STATUS',
        action='callback',
        callback=mitterlib.check_interfaces,
        callback_kwargs={'interface': 'tty'})
    group.add_option('--replies',
        dest='replies',
        help='Get a list of replies intead of the friends timeline',
        default=False,
        action='callback',
        callback=mitterlib.check_interfaces,
        callback_kwargs={'interface': 'tty', 'set': True})
    parser.add_option_group(group)
    return


class Interface(object):
    """The console/tty interface for Mitter."""

    def __init__(self, save_callback, username, password, https, connection, \
            prefs):
        """Class initialization."""

        self.log = logging.getLogger('ui.tty')
        self.twitter = connection
        self.save = save_callback
        self.username = username
        self.password = password
        self.https = https

        self.update = prefs.get('update', None)
        self.command = prefs.get('command', False)
        self.replies = prefs.get('replies', False)

        self.prefs = {
                'last_reply': int(prefs.get('last_reply', 0)),
                'last_id': int(prefs.get('last_id', 0))}

    def friends_timeline(self):
        """Starts the friends-timeline request."""
        self.twitter.friends_timeline(self._list_tweets)
        return

    def _list_tweets(self, data, error, watch_field='last_id'):
        """Function called by the twitter interface when it have all the
        friends timeline."""

        if error == 401:
            # Not authenticated
            print 'Authorization fail. Check your details:'
            console_utils.authorization(self.save, namespace, self.prefs,
                self.username, self.password, self.https)
            print 'Your configuration was saved. Call mitter again.'
            return

        if error:
            print 'Sorry, couldn\'t download your friends timeline.'
            return

        tweets = console_utils.print_tweets(data, self.prefs[watch_field])
        if tweets:
            self.prefs[watch_field] = tweets[-1]
            self.save(self.username, self.password, self.https, namespace, \
                self.prefs)

        return

    def update_status(self, message):
        """Update use status."""
        if len(message) > 160:
            # Twitter refuses such messages (or so says their documentation)
            print 'Your message have more than 160 characters and it is ' \
                    'very likely Twitter'
            print 'will refuse it.'
            print '(You can try shortening your URLs before posting.)'
            print
            print 'Your status was NOT updated.'
            return

        if len(message) > 140:
            print 'Your message have more than 140 characters and ' \
                    'Twitter may truncate it.'
            print 'It would still be visible in the website.'
            print '(You may be still good if you are sending a URL.)'
            answer = raw_input('Do you want to continue [Y/n]? ')
            if answer.lower() == 'n':
                return

        self.twitter.update(message, self.post_update)
        return

    def post_update(self, data, error):
        """Function called after we update the status on Twitter."""

        if error:
            print 'Twitter returned an error during update. Your status ' \
                    'was NOT updated.'
        else:
            print 'Your status was updated.'
        return

    def get_replies(self):
        """Get a list of replies to the user."""
        self.twitter.replies(self._list_tweets, watch_field='last_reply')
        return

    # functions required by mitter

    def __call__(self):
        """The callable function, used by mitter to start the interface."""

        if self.update:
            self.update_status(self.update)
            self.twitter.close()
            return

        if self.replies:
            self.get_replies()
            self.twitter.close()
            return

        self.friends_timeline()
        self.twitter.close()
        return
