#!/usr/bin/python
# -*- coding: utf-8 -*-

# Mitter, a Maemo client for Twitter.
# Copyright (C) 2007, 2008  Julio Biason
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

import datetime
import math
import time


# Adapted from
#  http://code.djangoproject.com/browser/django/trunk/django/utils/timesince.py
# My version expects time to be given in UTC & returns timedelta from UTC.


def pluralize(singular, plural, count):
    if count == 1:
        return singular
    else:
        return plural


def timesince(d, now=None):
    """
    Takes two datetime objects and returns the time between then and now
    as a nicely formatted string, e.g "10 minutes"
    Adapted from http://blog.natbat.co.uk/archive/2003/Jun/14/time_since
    """
    chunks = (
        (60 * 60 * 24 * 365, lambda n: pluralize('year', 'years', n)),
        (60 * 60 * 24 * 30, lambda n: pluralize('month', 'months', n)),
        (60 * 60 * 24 * 7, lambda n: pluralize('week', 'weeks', n)),
        (60 * 60 * 24, lambda n: pluralize('day', 'days', n)),
        (60 * 60, lambda n: pluralize('hour', 'hours', n)),
        (60, lambda n: pluralize('minute', 'minutes', n)))
    # Convert datetime.date to datetime.datetime for comparison
    if d.__class__ is not datetime.datetime:
        d = datetime.datetime(d.year, d.month, d.day)
    if now:
        t = now.timetuple()
    else:
        t = time.gmtime()
    now = datetime.datetime(t[0], t[1], t[2], t[3], t[4], t[5])

    # ignore microsecond part of 'd' since we removed it from 'now'
    delta = now - (d - datetime.timedelta(0, 0, d.microsecond))
    since = delta.days * 24 * 60 * 60 + delta.seconds
    if since <= 0:
        return 'moments'

    for i, (seconds, name) in enumerate(chunks):
        count = since / seconds
        if count != 0:
            break

    if count < 0:
        return '%d milliseconds' % math.floor((now - d).microseconds / 1000)

    s = '%d %s' % (count, name(count))
    if i + 1 < len(chunks):
        # Now get the second item
        seconds2, name2 = chunks[i + 1]
        count2 = (since - (seconds * count)) / seconds2
        if count2 != 0:
            s += ', %d %s' % (count2, name2(count2))
    return s


def timeuntil(d, now=None):
    """
    Like timesince, but returns a string measuring the time until
    the given time.
    """
    if now == None:
        now = datetime.datetime.now()
    return timesince(now, d)
