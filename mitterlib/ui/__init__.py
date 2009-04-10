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

import logging
import glob     # or should I use os.walk()?
import os.path

_log = logging.getLogger('ui.__init__')

interfaces = [
        'pygtk',
        'cmd',
        'tty']


def _import_name(interface):
    """Return the name of the module for that interface."""
    return 'mitterlib.ui.ui_%s' % (interface)


def _interface_list(prefer=None):
    """Return a list of UI modules."""
    if prefer:
        if prefer in interfaces:
            yield _import_name(prefer)

    for interface in interfaces:
        module_name = _import_name(interface)
        _log.debug('Module %s' % (module_name))
        yield module_name


def interface(prefer=None):
    """Try to find an interface that works in the current user system."""
    _log.debug('Preferred interface: %s' % (prefer))
    interface = None
    for module_name in _interface_list(prefer):
        # try to import each using __import__
        try:
            _log.debug('Trying to import %s' % (module_name))
            interface = __import__(module_name, fromlist=[module_name])
            break
        except ImportError, exc:
            _log.debug('Failed')
            _log.debug(str(exc))
            pass

    return interface


def interface_options(optparser):
    """Add options in the command line OptParser object for every
    interface (yes, every interface, even the ones the user doesn't care)."""

    available_interfaces = []
    for module in _interface_list():
        try:
            _log.debug('Importing %s for options' % (module))
            interface = __import__(module, fromlist=[module])

            interface.options(optparser)
            available_interfaces.append(module.split('_')[-1])
        except ImportError:
            pass    # so we don't care

    # update the help option for the '--interface' to list the known
    # interfaces

    interface_option = optparser.get_option('--interface')
    interface_option.help = ('Select an interface. Available interfaces: ' +
        ', '.join(available_interfaces))

    return
