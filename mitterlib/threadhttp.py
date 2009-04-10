#!/usr/bin/python
# -*- coding: utf-8 -*-

# Mitter, a Maemo client for Twitter.
# Copyright (C) 2007  Julio Biason
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

import threading
import urllib
import urllib2
import logging
import Queue
import re

try:
    # Python 2.6/3.0 JSON parser
    import json
except ImportError:
    # Fallback to SimpleJSON
    import simplejson as json

from httplib import BadStatusLine
from socket import error


class ThreadHTTP(threading.Thread):
    """Runs HTTP requests on threads."""

    # error codes send to requesters. Because we return the HTTP status
    # whenever possible, we'll use negative numbers to those errors.

    NETWORK_ERROR = -1
    DNS_ERROR = -2
    INVALID_RESPONSE = -3
    LOW_LEVEL_ERROR = -4

    def __init__(self, id, shared_queue=None):
        threading.Thread.__init__(self)
        self.setDaemon(False)
        self._id = id
        self._log = logging.getLogger('mitterlib.threadhttp.%d' % (id))
        if shared_queue:
            self.queue = shared_queue
        else:
            self.queue = Queue.Queue()

    def request(self, callback, url, headers=None, body=None, jsonify=True,
            *args, **kwargs):
        """Add a HTTP request to <server>, requesting <resource> in the queue
        pool. Once finished, call <callback>. Headers are optional. If there
        is <body>, do a POST request; otherwise, GET. <callback> must accept
        status, data and error (which can be None). If <jsonify> is True (the
        default), then convert the data to JSON before sending it to
        <callback>."""

        url = urllib.quote(url.encode('utf-8'), '/:?=')
        self.queue.put((callback, url, headers, body, jsonify, args, kwargs))

    def make_request(self, url, headers, body):
        """Make the actual request to the server."""
        request = urllib2.Request(url=url)
        if body:
            self._log.debug('Body: %s' % (body))
            request.add_data(body)

        for key in headers:
            self._log.debug('Header: %s=%s' % (key, headers[key]))
            request.add_header(key, headers[key])

        try:
            self._log.debug('Starting request of %s' % (url))
            response = urllib2.urlopen(request)
            data = response.read()
        except urllib2.HTTPError, exc:
            self._log.debug('HTTPError: %d' % (exc.code))
            self._log.debug('HTTPError: response body:\n%s'
                                    % exc.read())
            return (exc.code, None)
        except urllib2.URLError, exc:
            self._log.error('URL error: %s' % exc.reason)
            return (ThreadHTTP.DNS_ERROR, None)
        except BadStatusLine:
            self._log.error('Bad status line (Twitter is going bananas)')
            return (ThreadHTTP.INVALID_RESPONSE, None)
        except error:   # That's the worst exception ever.
            self._log.error('Socket connection error')
            return (ThreadHTTP.LOW_LEVEL_ERROR, None)

        self._log.debug('Request completed')

        return (None, data)

    def run(self):
        """Do the request to the server."""
        while 1:
            self._log.debug('Thread %d waiting for work' % (self._id))
            work = self.queue.get()
            if work is None:
                self._log.debug('Thread %d done' % (self._id))
                break

            (callback, url, headers, body, jsonify, args, kwargs) = work
            (status, data) = self.make_request(url, headers, body)

            if (not data) or (status and status != 200):
                self._log.info('Got HTTP Status %s from twitter.com' % status)
                self._log.debug('Request failed for callback handler: %s' %
                                            callback.__name__)
            elif jsonify:
                # Hack to fix invalid JSON from Twitter
                data = re.sub("Couldn't find Status with ID=([0-9]*),", '', \
                    data)
                try:
                    if hasattr(json, "loads"):
                        # JSON 1.9 keeps complaining to use load instead of
                        # read
                        data = json.loads(data)
                    else:
                        # JSON 1.7 still uses read
                        data = json.read(data)
                except Exception, e:
                    self._log.error('Exception while parsing json. %s' % e)
                    if 'HTTP-EQUIV="REFRESH"' in data:
                        # Twitter has this annoying habit of returning a
                        # 'please refresh' meta with a 200 HTTP Status instead
                        # of using a 503 status as mentioned in their API docs
                        status = 503
                    else:
                        status = str(e)
                    print data
                    data = None

            # that None there is the error response. Sorry, not implemented
            # yet (but I'll do it, I promise.)

            callback(data, status, *args, **kwargs)
        return
