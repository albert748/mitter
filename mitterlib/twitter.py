#!/usr/bin/python
# -*- coding: utf-8 -*-

# Mitter, a client for Twitter.
# Copyright (C) 2007, 2008 The Mitter Contributors
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

import urllib
import urllib2
import logging
import datetime
import threadhttp
import Queue
import base64

from constants import version


def _to_datetime(server_str):
    """Convert a date send by the server to a datetime object.
    Ex:
        from this:
            Tue Mar 13 00:12:41 +0000 2007
            to datetime.
    """
    month_names = [None, 'Jan', 'Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    date_info = server_str.split(' ')
    month = month_names.index(date_info[1])
    day = int(date_info[2])
    year = int(date_info[5])

    time_info = date_info[3].split(':')
    hour = int(time_info[0])
    minute = int(time_info[1])
    second = int(time_info[2])

    return datetime.datetime(year, month, day, hour, minute, second)


class Twitter(object):
    """Base class to talk to twitter."""

    _user_agent = 'Mitter %s' % (version)

    # error codes

    UNKNOWN_ERROR = -1
    LIMIT_EXCEEDED = 1

    def __init__(self, username, password, https=False, threads=2):
        """Class initialization."""

        self.username = username
        self.password = password
        self.https = https

        self.queue = Queue.Queue()
        self.log = logging.getLogger('mitterlib.twitter')

        self.workers = []

        if threads > 1:
            while threads > 0:
                self.log.debug('Starting worker %s' % (threads))

                worker = threadhttp.ThreadHTTP(threads, self.queue)
                worker.start()

                self.workers.append(worker)
                threads -= 1
        else:
            # with just one thread, we don't used threads at all. System will
            # work in a non-threaded way.
            worker = threadhttp.ThreadHTTP(0, self.queue)
            # no start
            self.workers.append(worker)

        return

    def _set_https(self, value):
        """Update the https value and also make sure the server URL is
        updated."""
        self._https = value
        self._set_server()

    def _get_https(self):
        return self._https

    https = property(_get_https, _set_https)

    def _set_server(self):
        """Decide what URL to use to talk to Twitter."""
        if self.https:
            self._server = 'https://twitter.com'
        else:
            self._server = 'http://twitter.com'

    def _common_headers(self):
        """Returns a string with the normal headers we should add on every
        request"""

        auth = base64.b64encode('%s:%s' % (self.username, self.password))

        headers = {
                'Authorization': 'Basic %s' % (auth),
                'User-Agent': self._user_agent}
        return headers

    def request(self, resource, callback, headers=None, body=None, *args,
            **kwargs):
        """Send a request to the Twitter server. Once finished, call the
        function at callback."""

        url = '%s%s.json' % (self._server, resource)
        self.log.debug('Request to %s' % (url))

        request_headers = self._common_headers()

        if headers:
            request_headers.update(headers)

        # since the queue is shared, we can call any of the worker threads.
        # And yes, I know this is fugly.

        worker = self.workers[0]
        worker.request(callback, url, request_headers, body, True, *args,
                **kwargs)

        if len(self.workers) == 1:
            # no threads, rememeber?
            self.queue.put(None)    # so it quits the loop
            worker.run()
        return

    def close(self):
        """Close the connection with Twitter."""
        # Internally, what we do is fill the Queue pool with Nones, so the
        # working threads stop and close.

        if len(self.workers) == 1:
            # no threads, so we just return
            return

        for a in xrange(len(self.workers)):
            self.log.debug('Adding NONE for the workers')
            self.queue.put(None)

        # And now wait for the threads to finish.

        self.log.debug('Waiting for workers to finish')
        for worker in self.workers:
            worker.join()

    def friends_timeline(self, callback, *args, **kwargs):
        """Retrieve the logged user friends timeline."""

        # because we want to make a nice dictionary for our users, we DON'T
        # call their callback; we set a callback inside this object which will
        # convert the 'created_at' field to a datetime and THEN call their
        # callback.

        self.request('/statuses/friends_timeline', self._update_fields,
                user_callback=callback, *args, **kwargs)
        return

    def _update_fields(self, data, error=None, user_callback=None,
            *args, **kwargs):
        """Called after we do a friends timeline request. We use it to convert
        the 'created_at' field to a datetime and convert HTML chars in the
        body."""

        if user_callback is None:
            self.log.debug('User_callback not set')
            return

        if error:
            # do not try to convert the data if there was any error in the
            # connection
            user_callback(data, error, *args, **kwargs)
            return

        if 'error' in data:
            self.log.debug('Twitter send us an error')
            # twitter send us an error!
            if 'Rate limit exceeded' in data['error']:   # this test is bad
                self.log.debug('Limit exceeded')
                error = self.LIMIT_EXCEEDED
            else:
                error = self.UNKNOWN_ERROR
                self.log.debug('Unkonwn error: %s' % (data['error']))
            user_callback([], error, *args, **kwargs)
            return

        for tweet in data:
            # XXX this is a good point to save the latest "created_at" we see,
            # so we can use this value in the next friends_timeline request
            # and get less data.

            created_at = tweet['created_at']
            self.log.debug('Created at: %s' % (created_at))
            tweet['created_at'] = _to_datetime(created_at)
            tweet['text'] = urllib2.unquote(tweet['text'])

        user_callback(data, error, *args, **kwargs)
        return

    def update(self, status, callback, *args, **kwargs):
        """Update the user status."""

        body = urllib.urlencode({'status': status, 'source': 'mitter'})
        self.log.debug('Message to twitter: %s' % (body))

        # same as the friends timeline, we call our own callback to convert
        # the 'created_at' field to a datetime

        self.request('/statuses/update', self.post_update,
                user_callback=callback, body=body, *args, **kwargs)
        return

    def post_update(self, response, error, user_callback, *args, **kwargs):
        """Function called after the update. We intercept this before calling
        the user callback to convert the 'created_at' field to a datetime
        object."""

        if response and 'created_at' in response:
            response['created_at'] = _to_datetime(response['created_at'])

        user_callback(response, error, *args, **kwargs)
        return

    def download(self, url, callback, *args, **kwargs):
        """Load an external element."""
        headers = self._common_headers()
        del headers['Authorization']    # why, we don't need that!

        worker = self.workers[0]
        worker.request(callback, url, headers, None, jsonify=False,
                *args, **kwargs)
        return

    def tweet_destroy(self, tweet_id, callback, *args, **kwargs):
        """Delete a tweet."""

        body = urllib.urlencode({'id': tweet_id}) # Force POST method
        resource = '/statuses/destroy/%s' % (tweet_id)
        data = self.request(resource, callback, body=body, *args, **kwargs)
        return

    def friends_list(self, callback, *args, **kwargs):
        """Get list of folks followed by user"""
        return self.request('/statuses/friends', callback, *args, **kwargs)

    def replies(self, callback, *args, **kwargs):
        """Get a list of replies to the authenticated user."""
        return self.request('/statuses/replies', self._update_fields,
                user_callback=callback, *args, **kwargs)

    def rate_limit_status(self, callback, *args, **kwargs):
        """Return the current user rate limit."""
        return self.request('/account/rate_limit_status', callback,
                *args, **kwargs)
