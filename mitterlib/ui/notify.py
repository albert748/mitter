#!/usr/bin/python
# -*- coding: utf-8 -*-

# Mitter, a Maemo client for Twitter.
# Copyright (C) 2007  Julio Biason, Deepak Sarda
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

import os
import subprocess
import logging
import re


class Notify():

    def __init__(self, appname, timeout=5):
        """appname: a string value specifying the name of the application
        sending the message.
        timeout: an integer value in seconds specifying the time for which
        a notification should be shown"""

        self.log = logging.getLogger('notify')
        self.appname = appname
        self.timeout = timeout
        self.notify = None

        try:
            import dbus
            bus = dbus.SessionBus()
            proxy = bus.get_object('org.freedesktop.Notifications',
                    '/org/freedesktop/Notifications')
            self._dbus_notify = dbus.Interface(proxy,
                    'org.freedesktop.Notifications')
            self.notify = self._notify_galago
            self.log.debug('Using Galago notifications')
        except:
            self.log.debug('Could not initialize Galago notification ' \
                    'interface')

        if not self.notify and os.getenv('KDE_FULL_SESSION'):
            self.notify = self._notify_kde
            self.log.debug('Using KDE notifications')

        if not self.notify:
            self.notify = self._notify_default
            self.log.debug('Using default notifications')

    def _notify_kde(self, msg, x, y):
        try:
            pid = subprocess.Popen(['kdialog', '--nograb', '--title',
                    self.appname,
                    '--geometry', '10x5+%d+%d' % (x, y),
                    '--passivepopup', str(msg), str(self.timeout)]).pid
        except Exception, e:
            self.log.error('error %s' % e)
            self._notify_default(msg, x, y)
        finally:
            del pid

    def _notify_galago(self, msg, x, y):
        msg = re.sub(r'<br\/?>', '', str(msg))
        msg = re.sub(r'&(?!amp;)', r'&amp;', msg)

        try:
            self._dbus_notify.Notify(self.appname, 0, '', self.appname, msg,
                    [], {'x': x, 'y': y}, 1000*self.timeout)
        except Exception, e:
            self.log.error('error %s' % e)
            self._notify_default(msg, x, y)

    def _notify_default(self, msg, x, y):
        self.log.info('notification: %s' % msg)
