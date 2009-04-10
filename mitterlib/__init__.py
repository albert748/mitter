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


from optparse import OptionValueError


def save_config(username, password, https=False, namespace=None,
        extra_data=None):
    """Utility function to all interfaces, to save user, password and more
    data, as the interface requests."""

    import ConfigParser
    import os
    import stat
    global config_file

    if not config_file:
        config_file = os.path.expanduser('~/.mitter.cfg')

    config = ConfigParser.ConfigParser()

    # read the config, so we don't lose any information that may be there
    # already

    try:
        config_fp = file(config_file, 'r')
        config.readfp(config_fp)
    except IOError:
        # the config file doesn't exist. It's no biggie, as we are creating a
        # new one anyway. The idea is just not to lose any other configs, but
        # there are no configs to be lost.
        pass

    # add the new data (or update the old one)

    if not config.has_section('Mitter'):
        config.add_section('Mitter')

    config.set('Mitter', 'username', username)
    config.set('Mitter', 'password', password)
    config.set('Mitter', 'https', https)

    if namespace and extra_data:
        if not config.has_section(namespace):
            config.add_section(namespace)

        for key in extra_data:
            config.set(namespace, key, extra_data[key])

    try:
        config_fp = file(config_file, 'w')
        os.chmod(config_file, stat.S_IRUSR|stat.S_IWUSR)
        config.write(config_fp)
        config_fp.close()
    except IOError:
        print 'Error writing config file: %s' % config_file

    return True


def read_config(conf_file=None, namespace=None):
    """Read the saved username and password."""

    import ConfigParser
    import os.path
    global config_file

    if conf_file:
        config_file = conf_file
    else:
        config_file = os.path.expanduser('~/.mitter.cfg')

    config = ConfigParser.ConfigParser()

    config_fp = file(config_file, 'r')
    config.readfp(config_fp)

    username = config.get('Mitter', 'username')
    password = config.get('Mitter', 'password')
    try:
        https = config.getboolean('Mitter', 'https')
    except ConfigParser.NoOptionError:
        # Older versions may not have this option in the config file
        https = False

    ui_prefs = {}
    if namespace and config.has_section(namespace):
        ui_prefs = dict(config.items(namespace))

    # return the username and password outside the interface preferences, as
    # they are needed for every interface.

    return (username, password, https, ui_prefs)


def find_image(image_name):
    """Using the iamge_name, search in the common places. Return the path for
    the image or None if the image couldn't be found."""

    # just because I'm a logging nut

    import logging
    log = logging.getLogger('mitterlib.find_image')

    import os
    import os.path
    import sys

    # the order is the priority, so keep global paths before local paths

    current_dir = os.path.abspath(os.path.dirname(__file__))

    common_paths = [
            os.path.join(sys.prefix, 'share', 'pixmaps'),
            os.path.join('.', 'pixmaps'),
            os.path.join(current_dir, '..', 'pixmaps')
            ]

    for path in common_paths:
        filename = os.path.join(path, image_name)
        log.debug('Checking %s...' % (filename))
        if os.access(filename, os.F_OK):
            log.debug('Default image is %s' % (filename))
            return filename

    return None


def check_interfaces(option, opt_str, value, parser, **kwargs):
    """User by the optparse object to check if all the options the user called
    belong to the same interface. This will also implicit select interfaces
    based on the options used."""

    if hasattr(parser.values, 'interface') and \
            parser.values.interface is not None:
        if ('interface' in kwargs) \
                (parser.values.interface != kwargs['interface']):
            print ('Mixed interfaces: %s - %s' % (
                parser.values.interface, kwargs['interface']))
            raise OptionValueError('You are mixing options from ' \
                    'different interfaces')
    elif 'interface' in kwargs:
        parser.values.interface = kwargs['interface']

    if not value:
        if 'set' in kwargs:
            value = kwargs['set']
    setattr(parser.values, option.dest, value)
    return
