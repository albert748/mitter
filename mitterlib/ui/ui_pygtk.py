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

import pygtk
pygtk.require('2.0')
import gtk
import gobject

gobject.threads_init()
gtk.gdk.threads_init()

import datetime
import re
import sys
import os
import os.path
import timesince
import logging

import mitterlib as util

from notify import Notify
from mitterlib.constants import gpl_3, version
from mitterlib.ui.utils import str_len

from optparse import OptionGroup

namespace = 'pygtk'
threads = 2


def options(parser):
    """Add the options for this interface."""
    group = OptionGroup(parser, 'PyGTK interface')
    group.add_option('--refresh-interval',
        dest='refresh_interface',
        help='Refresh interval',
        type='int',
        metavar='MINUTES',
        default=None,
        action='callback',
        callback=util.check_interfaces,
        callback_kwargs={'interface': namespace})
    parser.add_option_group(group)
    return

# Constants

MAX_STATUS_DISPLAY = 60

url_re = re.compile(r'(https?://[^\s\n\r]+)', re.I)

class Columns:
    (PIC, NAME, MESSAGE, USERNAME, ID, DATETIME, ALL_DATA) = range(7)


# This is the main class, used by the mitter executable to display the
# interface.


class Interface(object):

    """Linux/GTK interface for Mitter."""

    def __init__(self, save_callback, default_username, default_password, \
            https, connection, prefs):
        """Class initialization."""

        self.user_pics = {}
        self.pic_queue = set()

        self.log = logging.getLogger('ui.pygtk')
        self.last_update = None
        self.unread_tweets = 0

        self.https = https

        # ConfigParser likes to read everything as string, so we need to cast
        # the refresh interval to int

        self.prefs = {'width': int(prefs.get('width', 450)),
                      'height': int(prefs.get('height', 300)),
                      'position_x': int(prefs.get('position_x', 5)),
                      'position_y': int(prefs.get('position_y', 5)),
                      'refresh_interval': int(prefs.get('refresh_interval',
                          5))}

        # Load images
        self.app_icon = util.find_image('mitter.png')
        self.app_icon_alert = util.find_image('mitter-new.png')
        if self.app_icon and self.app_icon_alert:
            # if there are no icon files, there is no way to setup 
            # the systray 
            self.systray_setup()
        else:
            self.systray = None
        
        good_image = util.find_image('unknown.png')
        if good_image:
            self.default_pixmap = gtk.gdk.pixbuf_new_from_file(good_image)
        else:
            self.default_pixmap = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,
                    has_alpha=False, bits_per_sample=8, width=48, height=48)

        # other pixmaps used in the interface
        pixbuf_delete_path = util.find_image('icon_trash.gif')
        if pixbuf_delete_path:
            self.pixbuf_delete = gtk.gdk.pixbuf_new_from_file(
                    pixbuf_delete_path)

        pixbuf_reply_path = util.find_image('reply.png')
        if pixbuf_reply_path:
            self.pixbuf_reply = gtk.gdk.pixbuf_new_from_file(
                    pixbuf_reply_path)


        self.main_window(self.prefs['width'], self.prefs['height'],
                         self.prefs['position_x'], self.prefs['position_y'])

        self.add_grid()
        update_box = self.create_update_box()

        # update the char count

        self.count_chars(self.update_text)

        # statusbar

        self.statusbar = gtk.Statusbar()
        self.statusbar.show()

        self.statusbar_context = self.statusbar.get_context_id(
                'Welcome to Mitter')

        # scrollbars for the grid

        self.menu_and_toolbar()

        scrolled_window = gtk.ScrolledWindow()
        scrolled_window.set_policy(gtk.POLICY_NEVER, gtk.POLICY_ALWAYS)
        scrolled_window.add(self.grid)

        # the update field

        box = gtk.VBox(False, 1)
        box.pack_start(self.main_menu, False, True, 0)
        box.pack_start(scrolled_window, True, True, 0)
        box.pack_start(update_box, False, True, 0)
        box.pack_start(self.statusbar, False, False, 0)
        self.window.add(box)

        # settings window

        self.create_settings_dialog()
        self.username_field.set_text(default_username)
        self.password_field.set_text(default_password)
        self.https_field.set_active(self.https)

        # notification helper
        self.notify_broadcast = Notify('mitter').notify

        # callbacks

        self.save_callback = save_callback

        # our connection with twitter

        self.twitter = connection

        # start auto refresh activity

        self._refresh_id = None
        self.set_auto_refresh()

        self.window.set_focus(self.update_text)
        return

    # ------------------------------------------------------------
    # Window creation functions
    # ------------------------------------------------------------

    def main_window(self, initial_width, initial_height,
                            initial_pos_x, initial_pos_y):
        """Creates the main window and set its properties."""

        # add a horizontal split. The tweets grid go in the top, the update
        # field goes in the bottom.

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.connect('destroy', self.quit)
        self.window.connect('delete-event', self.delete_event_cb)
        self.window.connect('focus-in-event', self.notify_reset)
        self.window.set_title('Mitter')
        self.window.set_size_request(10, 10)    # very small minimal size
        self.window.resize(initial_width, initial_height)
        self.window.move(initial_pos_x, initial_pos_y)

        # connect the signal when the window is resized, so we can update the
        # size of the word wrap in the grid.

        self.window.connect('size-request', self.size_request)

        # icon

        if self.app_icon:
            self.window.set_icon_from_file(self.app_icon)
        return

    def systray_setup(self):
        self.systray = gtk.StatusIcon()
        self.systray.set_from_file(self.app_icon)
        self.systray.connect('activate', self.systray_cb)
        self.systray.connect('popup-menu', self.systray_popup)
        self.systray.set_tooltip('Mitter: Click to toggle window visibility.')
        self.systray.set_visible(True)
        return
        
    def systray_popup(self, status_icon, button, activate_time):
	  popup_menu = gtk.Menu()
	  restore_item = gtk.MenuItem("Restore")
	  restore_item.connect("activate", self.systray_cb)
	  quit_item = gtk.ImageMenuItem(gtk.STOCK_QUIT)
	  quit_item.connect("activate", self.quit)
	  popup_menu.append(restore_item)
	  popup_menu.append(quit_item)
	  popup_menu.show_all()
	  time = gtk.get_current_event_time()
	  popup_menu.popup(None, None, None, 0, time)

    def delete_event_cb(self, widget, event, user_param=None):
        if self.systray:
            if self.systray.is_embedded():
                self.window.hide()
            else:
                self.quit(widget)
        else:
            self.quit(widget)
        return True

    def systray_cb(self, widget, user_param=None):
        if self.window.get_property('visible'):
            x, y = self.window.get_position()
            self.prefs['position_x'] = x
            self.prefs['position_y'] = y
            self.window.hide()
        else:
            self.window.move(
                    self.prefs['position_x'],
                    self.prefs['position_y'])
            self.window.deiconify()
            self.window.present()

    def create_settings_dialog(self):
        """Creates the settings dialog."""

        self.settings_window = gtk.Dialog(title="Settings",
                parent=self.window, flags=gtk.DIALOG_MODAL |
                gtk.DIALOG_DESTROY_WITH_PARENT,
                buttons=(gtk.STOCK_CANCEL, 0, gtk.STOCK_OK, 1))
        self.settings_box = gtk.Table(rows=4, columns=2, homogeneous=False)

        username_label = gtk.Label('Username:')
        password_label = gtk.Label('Password:')
        refresh_label = gtk.Label('Refresh interval (minutes):')
        https_label = gtk.Label('Use secure connections (HTTPS):')

        self.username_field = gtk.Entry()
        self.password_field = gtk.Entry()
        self.password_field.set_visibility(False)

        self.refresh_interval_field = gtk.SpinButton()
        self.refresh_interval_field.set_range(1, 99)
        self.refresh_interval_field.set_numeric(True)
        self.refresh_interval_field.set_value(self.prefs['refresh_interval'])
        self.refresh_interval_field.set_increments(1, 5)

        self.https_field = gtk.CheckButton()
        self.https_field.set_active(self.https)

        self.settings_box.attach(username_label, 0, 1, 0, 1)
        self.settings_box.attach(self.username_field, 1, 2, 0, 1)
        self.settings_box.attach(password_label, 0, 1, 1, 2)
        self.settings_box.attach(self.password_field, 1, 2, 1, 2)
        self.settings_box.attach(refresh_label, 0, 1, 2, 3)
        self.settings_box.attach(self.refresh_interval_field, 1, 2, 2, 3)
        self.settings_box.attach(https_label, 0, 1, 3, 4)
        self.settings_box.attach(self.https_field, 1, 2, 3, 4)

        self.settings_box.show_all()
        self.settings_window.vbox.pack_start(self.settings_box, True,
                True, 0)
        self.settings_window.connect('close', self.close_dialog)
        self.settings_window.connect('response', self.update_preferences)

        return

    def show_about(self, widget):
        """Show the about dialog."""

        about_window = gtk.AboutDialog()
        about_window.set_name('Mitter')
        about_window.set_version(version)
        about_window.set_copyright('2007-2008 Mitter Contributors')
        about_window.set_license(gpl_3)
        about_window.set_website('http://mitter.googlecode.com')
        about_window.set_website_label('Mitter on GoogleCode')
        about_window.set_authors(['Julio Biason', 'Deepak Sarda', \
            'Gerald Kaszuba'])
        about_window.connect('close', self.close_dialog)
        about_window.run()
        about_window.hide()


    # ------------------------------------------------------------
    # Widget creation functions
    # ------------------------------------------------------------

    def add_grid(self):
        """Add the displaying grid."""

        self.grid_store = gtk.ListStore(str, str, str, str, str, object,
                object)

        self.grid_store.set_sort_func(Columns.DATETIME, self.sort_by_time)
        self.grid_store.set_sort_column_id(Columns.DATETIME,
                gtk.SORT_DESCENDING)

        self.grid = gtk.TreeView(self.grid_store)
        self.grid.set_property('headers-visible', False)
        self.grid.set_rules_hint(True)  # change color for each row

        self.user_renderer = gtk.CellRendererPixbuf()
        self.user_column = gtk.TreeViewColumn('User', self.user_renderer)
        self.user_column.set_cell_data_func(self.user_renderer,
                self.cell_renderer_user)
        self.grid.append_column(self.user_column)

        self.message_renderer = gtk.CellRendererText()
        #self.message_renderer.set_property('wrap-mode', gtk.WRAP_WORD)
        self.message_renderer.set_property('wrap-width', 200)
        self.message_renderer.set_property('width', 10)

        self.message_column = gtk.TreeViewColumn('Message',
                self.message_renderer, text=1)
        self.message_column.set_cell_data_func(self.message_renderer,
                self.cell_renderer_message)
        self.grid.append_column(self.message_column)
        self.grid.set_resize_mode(gtk.RESIZE_IMMEDIATE)
        self.grid.connect('cursor-changed', self.check_post)
        self.grid.connect('row-activated', self.open_post)
        self.grid.connect('button-press-event', self.click_post)
        
        #Maybe here is no use
        #self.grid.connect('popup-menu',
        #        lambda view: self.show_post_popup(view, None))

    def menu_and_toolbar(self):
        """Created the main menu and the toolbar."""

        # tasks (used by the menu and toolbar)

        refresh_action = gtk.Action('Refresh', '_Refresh',
                'Update the listing', gtk.STOCK_REFRESH)
        refresh_action.connect('activate', self.refresh)

        quit_action = gtk.Action('Quit', '_Quit',
                'Exit Mitter', gtk.STOCK_QUIT)
        quit_action.connect('activate', self.quit)

        settings_action = gtk.Action('Settings', '_Settings',
                'Settings', gtk.STOCK_PREFERENCES)
        settings_action.connect('activate', self.show_settings)

        delete_action = gtk.Action('Delete', '_Delete', 'Delete a post',
                gtk.STOCK_DELETE)
        delete_action.set_property('sensitive', False)
        delete_action.connect('activate', self.delete_tweet)

        about_action = gtk.Action('About', '_About', 'About Mitter',
                gtk.STOCK_ABOUT)
        about_action.connect('activate', self.show_about)

        shrink_url_action = gtk.Action('ShrinkURL', 'Shrink _URL',
                'Shrink selected URL', gtk.STOCK_EXECUTE)
        shrink_url_action.connect('activate', self.shrink_url)

        post_action = gtk.Action('Posts', '_Posts', 'Post management', None)
        
        hidemenu_action = gtk.ToggleAction('HideMemubar', 'Hide _Menubar',
        		'Hide Menubar', gtk.STOCK_GOTO_TOP)
        hidemenu_action.connect('activate', self.hide_menu)
        
        hidewindow_action = gtk.Action("HideWindow", "Hide _Window",
        		"Hide Window", gtk.STOCK_NO)
        hidewindow_action.connect('activate', self.systray_cb)

        file_action = gtk.Action('File', '_File', 'File', None)
        edit_action = gtk.Action('Edit', '_Edit', 'Edit', None)
        view_action = gtk.Action('View', '_View', 'View', None)
        help_action = gtk.Action('Help', '_Help', 'Help', None)

        # action group (will have all the actions, 'cause we are not actually
        # grouping them, but Gtk requires them that way)

        self.action_group = gtk.ActionGroup('MainMenu')
        self.action_group.add_action_with_accel(refresh_action, 'F5')
        # None = use the default acceletator
        self.action_group.add_action_with_accel(quit_action, None)
        self.action_group.add_action(settings_action)
        self.action_group.add_action(delete_action)
        self.action_group.add_action(post_action)
        self.action_group.add_action(file_action)
        self.action_group.add_action(edit_action)
        self.action_group.add_action(view_action)
        self.action_group.add_action(help_action)
        self.action_group.add_action(about_action)
        self.action_group.add_action_with_accel(shrink_url_action, '<Ctrl>U')
        self.action_group.add_action_with_accel(hidemenu_action, '<Alt>9')
        self.action_group.add_action_with_accel(hidewindow_action, '<Alt>x')

        # definition of the UI

        self.uimanager = gtk.UIManager()
        self.uimanager.insert_action_group(self.action_group, 0)
        ui = '''
        <ui>
          <toolbar name="MainToolbar">
            <toolitem action="Refresh" />
            <separator />
            <toolitem action="Delete" />
            <separator />
            <toolitem action="Settings" />
            <toolitem action="Quit" />
          </toolbar>
          <menubar name="MainMenu">
            <menu action="File">
              <menuitem action="Quit" />
            </menu>
            <menu action="Edit">
              <menuitem action="Refresh" />
              <menuitem action="Delete" />
              <menuitem action="ShrinkURL" />
              <separator />
              <menuitem action="Settings" />
            </menu>
            <menu action="View">
              <menuitem action="HideMemubar" />
              <menuitem action="HideWindow" />
            </menu>
            <menu action="Help">
              <menuitem action="About" />
            </menu>
          </menubar>
        </ui>
        '''
        self.uimanager.add_ui_from_string(ui)

        self.window.add_accel_group(self.uimanager.get_accel_group())

        self.main_toolbar = self.uimanager.get_widget('/MainToolbar')
        self.main_menu = self.uimanager.get_widget('/MainMenu')

        return

    def hide_menu(self, widget):
		  self.main_menu = self.uimanager.get_widget('/MainMenu')
		  if widget.get_active():
		      self.main_menu.hide()
		  else:
		      self.main_menu.show()

    def create_update_box(self):
        """Create the widgets related to the update box"""

        # username auto-completion (when doing replies)

        self.completion = gtk.EntryCompletion()
        self.friends_store = gtk.ListStore(str)
        self.completion.set_model(self.friends_store)
        self.completion.set_text_column(0)
        self.completion.set_minimum_key_length(1)

        # the field

        self.update_text = gtk.Entry()
        self.update_text.connect('activate', self.update_status)
        self.update_text.connect('changed', self.count_chars)
        self.update_text.set_completion(self.completion)
        settings = self.update_text.get_settings()
        settings.set_property('gtk-entry-select-on-focus', False)

        # ok, so now we do this:
        # 1) we split the left side to put, horizontally, some text and the
        # entry field
        # 2) the "Add" goes in the right side
        # (we do this 'cause, when someone is using small fonts, the button
        # gets bigger than the entry field and it looks a little bit weird.)

        #info_area = gtk.HBox(True, 0)

        self.char_count = gtk.Label()
        #I don't like this
        #info_area.pack_start(gtk.Label('What are you doing?'))
        #info_area.pack_start(self.char_count)

        text_area = gtk.VBox(True, 0)
        #text_area.pack_start(info_area)
        text_area.pack_start(self.update_text)

        self.update_button = gtk.Button()
        self.update_button.set_size_request(45,10)
        self.update_button.connect('clicked', self.update_status)
        
        image = gtk.Image()
        refresh_icon = util.find_image('refresh.png')
        image.set_from_file(refresh_icon)
        refresh_button = gtk.Button()
        refresh_button.add(image)
        refresh_button.set_size_request(30,10)
        refresh_button.connect("clicked", self.refresh)
        

        update_box = gtk.HBox(False, 0)
        update_box.pack_start(refresh_button, False, False, 0)
        update_box.pack_start(text_area, expand=True, fill=True,
                padding=0)
        update_box.pack_start(self.update_button, expand=False, fill=False,
                padding=0)

        return update_box


    # ------------------------------------------------------------
    # Grid cell content callback
    # ------------------------------------------------------------

    def sort_by_time(self, model, iter1, iter2, data=None):
        """The sort function where we sort by the datetime.datetime object"""

        d1 = model.get_value(iter1, Columns.DATETIME)
        d2 = model.get_value(iter2, Columns.DATETIME)

        # Why do we get called with None values?!

        if not d1:
            return 1
        if not d2:
            return -1

        if d1 < d2:
            return -1
        elif d1 > d2:
            return 1
        return 0

    def cell_renderer_user(self, column, cell, store, position):
        """Callback for the user column. Used to created the pixbuf of the
        userpic."""

        pic = store.get_value(position, Columns.PIC)
        if not pic in self.user_pics:
            cell.set_property('pixbuf', self.default_pixmap)

            # just make sure we download this pic too.
            self.queue_pic(pic)
        else:
            cell.set_property('pixbuf', self.user_pics[pic])

        return

    def cell_renderer_message(self, column, cell, store, position):
        """Callback for the message column. We need this to adjust the markup
        property of the cell, as setting it as text won't do any markup
        processing."""

        user = store.get_value(position, Columns.NAME)
        message = store.get_value(position, Columns.MESSAGE)
        time = store.get_value(position, Columns.DATETIME)
        username = store.get_value(position, Columns.USERNAME)

        time = timesince.timesince(time)

        # unescape escaped entities that pango is okay with
        message = re.sub(r'&(?!(amp;|gt;|lt;|quot;|apos;))', r'&amp;', message)

        # highlight URLs
        message = url_re.sub(r'<span foreground="blue">\1</span>',
                            message)

        # use a different highlight for the current user
        message = re.sub(r'(@'+self.twitter.username+')',
                r'<span foreground="#FF6633">\1</span>',
                message)

        markup = '<b>%s</b> <small>(%s)</small>:\n%s\n<small>%s</small>' % \
                (user, username, message, time)
        cell.set_property('markup', markup)

        return

    def cell_renderer_delete(self, column, cell, store, position):
        """Callback for the delete column. This column is used to display the
        delete tweet option, if the tweet belongs to the user."""

        username = store.get_value(position, Columns.USERNAME)
        if username == self.username_field.get_text():
            cell.set_property('pixbuf', self.pixbuf_delete)
        return

    def cell_renderer_reply(self, column, cell, store, position):
        """Callback for the reply column. This column is used to display the
        reply option, if the weet doesn't belong to the user."""

        username = store.get_value(position, Columns.USERNAME)
        if not username == self.username_field.get_text():
            cell.set_property('pixbuf', self.pixbuf_reply)
        return


    # ------------------------------------------------------------
    # All other callback functions
    # ------------------------------------------------------------

    # Non-widget attached callbacks

    def set_auto_refresh(self):
        """Configure auto-refresh of tweets every `interval` minutes"""

        if self._refresh_id:
            gobject.source_remove(self._refresh_id)

        self._refresh_id = gobject.timeout_add(
                self.prefs['refresh_interval']*60*1000,
                self.refresh, None)

        return

    def update_friends_list(self):
        """Fetch the user's list of twitter friends and add it
        to the friends_store for @reply autocompletion"""

        self.log.debug('Checking friends list...')
        friends = self.twitter.friends_list(self.post_update_friends_list)
        return

    def post_update_friends_list(self, friends, error):
        """Function called after we fetch the friends list."""

        self.log.debug('Received the friends list')

        if error == 401:    # XXX: Constants for this?
            # not authorized
            self.log.error('User is not authorized yet')
            return

        if error == 502 or error == 503:
            self.log.error('Twitter asked us to try getting friends list' \
                                    ' sometime later')
            gobject.timeout_add(5*60*1000, self.update_friends_list)
            return

        if error:
            # any error
            # well, we just don't add any friends, then.
            self.log.error('Error getting friend list, leaving list empty')
            return

        # I'm not really sure if we need to set the thread locking here (as we
        # are just updating the store), but better safe than sorry!

        gtk.gdk.threads_enter()
        for friend in friends:
            try:
                screen_name = '@' + friend['screen_name'] + ': '
                self.log.debug('Adding "%s" to the list' % (screen_name))
                self.friends_store.append([screen_name])
            except Exception, e:
                # No `error` does not always mean twitter sent us good data
                self.log.error('Error processing friend list. %s' % str(e))

        gtk.gdk.threads_leave()

        self.log.debug('List complete')

        return

    def prune_grid_store(self):
        """Prune the grid_store by removing the oldest rows."""

        if len(self.grid_store) <= MAX_STATUS_DISPLAY:
            return True # Required by gobject.idle_add() for this to be called
                        # again

        self.log.debug("prune_grid_store called")

        gtk.gdk.threads_enter()

        self.grid.freeze_child_notify()
        self.grid.set_model(None)

        # Since I don't know how to get the last row in grid_store,
        # I'll reverse the list and then pop out the first row instead.

        self.grid_store.set_sort_column_id(Columns.DATETIME,
                gtk.SORT_ASCENDING)

        iter = self.grid_store.get_iter_first()

        while (len(self.grid_store) > MAX_STATUS_DISPLAY) and iter:
            self.log.debug("popping off tweet with id %s" %
                            self.grid_store.get_value(iter, Columns.ID))
            self.grid_store.remove(iter) # iter is auto set to next row


        self.grid_store.set_sort_column_id(Columns.DATETIME,
                gtk.SORT_DESCENDING)
        self.grid.set_model(self.grid_store)
        self.grid.thaw_child_notify()

        gtk.gdk.threads_leave()
        return True

    # Main window callbacks

    def size_request(self, widget, requisition, data=None):
        """Callback when the window changes its sizes. We use it to set the
        proper word-wrapping for the message column."""

        self.prefs['width'], self.prefs['height'] = self.window.get_size()

        # this is based on a mail of Kristian Rietveld, on gtk maillist

        if not len(self.grid_store):
            # nothing to rearrange
            return

        column = self.message_column
        iter = self.grid_store.get_iter_first()
        path = self.grid_store.get_path(iter)

        column_rectangle = self.grid.get_cell_area(path, column)

        width = column_rectangle.width
        self.log.debug('Width=%d' % (width))

        # there should be only
        renderers = column.get_cell_renderers()
        for render in renderers:
            self.log.debug('Render update')
            render.set_property('wrap-width', width)

        while iter:
            #self.log.debug('Row changed')
            path = self.grid_store.get_path(iter)
            self.grid_store.row_changed(path, iter)
            iter = self.grid_store.iter_next(iter)

        return

    def quit(self, widget, user_data=None):
        """Callback when the window is destroyed (e.g. when the user closes
        the application."""
        
        # this is really annoying: if the threads are locked doing some IO
        # requests, the application will not quit. Displaying this message is
        # the only option we have right now.
        self.statusbar.push(self.statusbar_context,
                'Finishing tasks and saving preferences...')

        self.log.debug('quit callback invoked. exiting now...')
        self.save_interface_prefs()
        self.twitter.close()
        gtk.main_quit()

    def notify_reset(self, widget, event, user_data=None):
        if getattr(event, 'in_', False):
            self.window.set_urgency_hint(False)
            if self.systray:
                self.systray.set_tooltip('Mitter: Click to toggle ' \
                        'window visibility.')
                self.systray.set_from_file(self.app_icon)
            self.unread_tweets = 0
        return

    def notify(self, new_tweets=0):
        """Set the window hint as urgent, so Mitter window will flash,
        notifying the user about the new messages. Also send a notification
        message with one of the new tweets."""
        self.window.set_urgency_hint(True)
        if self.systray and self.unread_tweets > 0:
            self.systray.set_tooltip('Mitter: %s new' % self.unread_tweets)
            self.systray.set_from_file(self.app_icon_alert)

        if new_tweets and len(self.grid_store) > 0:
            iter = self.grid_store.get_iter_first()
            while iter:
                sender = self.grid_store.get_value(iter, Columns.USERNAME)
                if sender == self.username_field.get_text():
                    iter = self.grid_store.iter_next(iter)
                    continue
                else:
                    tweet = self.grid_store.get_value(iter, Columns.MESSAGE)
                    # Add avatar to notify message
                    pic = self.grid_store.get_value(iter, Columns.PIC)
                    self.queue_pic(pic)
                    avatar = self.user_pics[pic]
                    self.log.debug('notify_broadcast with this tweet: %s' %
                            tweet)
                    break

            if new_tweets > 1:
                msg = '<b>%d</b> unread tweets including ' \
                        'this from <i>%s</i>:<br/>%s' % (self.unread_tweets,
                                sender, tweet)
            else:
                msg = '<i>%s</i>:<br/>%s' % (sender,
                        tweet)

            if self.systray:
                gtk.gdk.threads_enter()
                geometry = self.systray.get_geometry()
                gtk.gdk.threads_leave()

                if geometry:
                    # there is no geometry on OS X
                    (screen, rect, orientation) = geometry
                    self.notify_broadcast(msg, avatar, rect.x, rect.y)
        return

    # settings callbacks

    def show_settings(self, widget, user_data=None):
        """Create and display the settings window."""

        self.settings_window.show()
        self.settings_window.run()

        return

    def close_dialog(self, user_data=None):
        """Hide the dialog window."""

        return True

    def update_preferences(self, widget, response_id=0, user_data=None):
        """
        Update the user preferences when the user press the "OK" button in the
        settings window."""

        if response_id == 1:
            self.statusbar.push(self.statusbar_context,
                    'Saving your profile...')

            self.save_interface_prefs()

            # update the (internal) twitter prefences too!

            self.twitter.username = self.username_field.get_text()
            self.twitter.password = self.password_field.get_text()
            self.twitter.https = self.https_field.get_active()
            refresh_interval = self.refresh_interval_field.get_value_as_int()
            self.prefs['refresh_interval'] = refresh_interval

            # update the list

            self.refresh(None)
            self.update_friends_list()
            self.statusbar.pop(self.statusbar_context)

            # update auto-refresh

            self.set_auto_refresh()

        self.settings_window.hide()

        return True


    # update status

    def update_status(self, user_data=None):
        """Update the user status on Twitter."""

        status = self.update_text.get_text()
        status = status.strip()
        if not str_len(status):
            return

        self.update_text.set_sensitive(False)
        self.statusbar.push(self.statusbar_context, 'Updating your status...')

        if str_len(status) > 140:
            error_message = 'Your message has more than 140 characters and' \
                    ' Twitter may truncate it. It would still be visible ' \
                    'on the website. Do you still wish to go ahead?'
            if str_len(status) > 160:
                error_message = 'Your message has more than 160 characters ' \
                        'and it is very likely Twitter will refuse it. You ' \
                        'can try shortening  your URLs before posting. Do ' \
                        'you still wish to go ahead?'

            error_dialog = gtk.MessageDialog(parent=self.window,
                    type=gtk.MESSAGE_QUESTION,
                    flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                    message_format="Your status update message is too long.",
                    buttons=gtk.BUTTONS_YES_NO)
            error_dialog.format_secondary_text(error_message)

            response = error_dialog.run()
            error_dialog.destroy()
            if response == gtk.RESPONSE_NO:
                self.statusbar.pop(self.statusbar_context)
                self.update_text.set_sensitive(True)
                self.window.set_focus(self.update_text)
                return

        data = self.twitter.update(status, self.post_update_status)

    def post_update_status(self, data, error):
        """Function called after we receive the answer from the update
        status."""

        if error:
            gtk.gdk.threads_enter()
            error_dialog = gtk.MessageDialog(parent=self.window,
                    type=gtk.MESSAGE_ERROR,
                    message_format='Error updating status. Please try again.',
                    buttons=gtk.BUTTONS_OK)
            error_dialog.connect("response", lambda *a:
                    error_dialog.destroy())
            error_dialog.run()
            gtk.gdk.threads_leave()
        else:
            if data:
                # i wonder if this will really work
                self.post_refresh([data], None, False)
            else:
                self.refresh(None, False)

            gtk.gdk.threads_enter()
            self.update_text.set_text("")
            gtk.gdk.threads_leave()

        gtk.gdk.threads_enter()
        self.statusbar.pop(self.statusbar_context)
        self.update_text.set_sensitive(True)
        self.window.set_focus(self.update_text)
        gtk.gdk.threads_leave()

        return True

    def count_chars(self, widget):
        """Count the number of chars in the edit field and update the
        label that shows the available space."""

        self.update_button.set_label('%d' % (140 -
            str_len(self.update_text.get_text())))

        return True

    def shrink_url(self, widget, user_data=None):
        bounds = self.update_text.get_selection_bounds()
        if not bounds:
            return
        else:
            start, end = bounds

        longurl = self.update_text.get_chars(start, end).strip()
        if not longurl:
            return

        self.log.debug('shrink url request for: %s' % longurl)

        self.update_text.set_sensitive(False)
        self.statusbar.push(self.statusbar_context, 'Shrinking URL...')

        self.twitter.download('http://is.gd/api.php?longurl=' + longurl,
                               self.post_shrink_url, longurl=longurl,
                               start=start, end=end)

    def post_shrink_url(self, url, error, longurl, start, end):
        if error:
            self.log.error("Exception in shrinking url. ' \
                    'Error code: %s" % error)
            # error dialog
            gtk.gdk.threads_enter()
            error_dialog = gtk.MessageDialog(parent=self.window,
                type=gtk.MESSAGE_ERROR,
                message_format='Failed to shrink the URL %s' % longurl,
                buttons=gtk.BUTTONS_OK)
            error_dialog.connect("response", lambda *a:
                    error_dialog.destroy())
            error_dialog.run()
            gtk.gdk.threads_leave()
        else:
            self.log.debug('Got shrunk url: %s' % url)
            char = self.update_text.get_chars(start-1, start)
            if start and not char.isspace():
                url = ' '+url
            char = self.update_text.get_chars(end, end+1)
            if not char.isspace():
                url = url+' '

            gtk.gdk.threads_enter()
            self.update_text.delete_text(start, end)
            self.update_text.insert_text(url, start)
            self.update_text.set_position(start+len(url))
            gtk.gdk.threads_leave()

        gtk.gdk.threads_enter()
        self.statusbar.pop(self.statusbar_context)
        self.update_text.set_sensitive(True)
        self.update_text.grab_focus()
        gtk.gdk.threads_leave()

    # post related callbacks

    def reply_tweet(self, widget, user_data=None):
        """Reply by putting the username in your input"""
        cursor = self.grid.get_cursor()
        if not cursor:
            return

        path = cursor[0]
        iter = self.grid_store.get_iter(path)
        username = self.grid_store.get_value(iter, Columns.USERNAME)
        text_insert = '@%s: ' % (username)

        self.log.debug('Inserting reply text: %s' % (text_insert))

        status = self.update_text.get_text()
        status = text_insert + status
        self.update_text.set_text(status)
        self.window.set_focus(self.update_text)
        self.update_text.set_position(len(status))

    def retweet(self, widget, user_data=None):
        """Retweet by putting the string rt and username in your input"""

        cursor = self.grid.get_cursor()
        if not cursor:
            return

        path = cursor[0]
        iter = self.grid_store.get_iter(path)
        username = self.grid_store.get_value(iter, Columns.USERNAME)
        msg = self.grid_store.get_value(iter, Columns.MESSAGE)
        text_insert = 'RT @%s: %s' % (username, msg)

        self.log.debug('Inserting retweet text: %s' % (text_insert))

        status = text_insert + self.update_text.get_text()
        self.update_text.set_text(status)
        self.window.set_focus(self.update_text)
        self.update_text.set_position(str_len(status))

    def delete_tweet(self, widget, user_data=None):
        """Delete a twit."""

        cursor = self.grid.get_cursor()
        if not cursor:
            return

        path = cursor[0]
        iter = self.grid_store.get_iter(path)
        tweet_id = int(self.grid_store.get_value(iter, Columns.ID))
        self.log.debug('Deleting tweet: %d' % (tweet_id))

        self.statusbar.push(self.statusbar_context, 'Deleting tweet...')

        self.twitter.tweet_destroy(tweet_id, self.post_delete_tweet,
                tweet=tweet_id)

        return

    def post_delete_tweet(self, data, error, tweet):
        """Function called after we delete a tweet on the server."""

        if error:
            gtk.gdk.threads_enter()
            error_dialog = gtk.MessageDialog(parent=self.window,
                    type=gtk.MESSAGE_ERROR,
                    message_format='Error deleting tweet. Please try again.',
                    buttons=gtk.BUTTONS_OK)
            error_dialog.connect("response", lambda *a:
                    error_dialog.destroy())
            error_dialog.run()
            gtk.gdk.threads_leave()
        else:
            # locate that tweet in the store and remove it.
            iter = self.grid_store.get_iter_first()
            tweet = int(tweet)
            while iter:
                id = self.grid_store.get_value(iter, Columns.ID)
                if int(id) == tweet:
                    self.grid_store.remove(iter)
                    break
                iter = self.grid_store.iter_next(iter)

        # update the interface
        gtk.gdk.threads_enter()
        self.statusbar.pop(self.statusbar_context)
        self.grid.queue_draw()
        gtk.gdk.threads_leave()

        return

    def check_post(self, treeview, user_data=None):
        """Callback when one of the rows is selected."""
        cursor = treeview.get_cursor()
        if not cursor:
            return

        path = cursor[0]
        iter = self.grid_store.get_iter(path)
        username = self.grid_store.get_value(iter, Columns.USERNAME)

        delete_action = self.action_group.get_action('Delete')

        if username == self.username_field.get_text():
            delete_action.set_property('sensitive', True)
        else:
            delete_action.set_property('sensitive', False)

        return

    def open_post(self, treeview, path, view_column, user_data=None):
        """Callback when one of the rows in activated."""

        iter = self.grid_store.get_iter(path)
        username = self.grid_store.get_value(iter, Columns.USERNAME)
        tweet_id = self.grid_store.get_value(iter, Columns.ID)
        message = self.grid_store.get_value(iter, Columns.MESSAGE)
        urls = url_re.search(message)
        if urls:
            # message contains a link; go to the link instead
            url = urls.groups()[0]
        else:
            url = 'http://twitter.com/%s/statuses/%s/' % (username, tweet_id)

        self.open_url(path, url)

    def click_post(self, treeview, event, user_data=None):
        """Callback when a mouse click event occurs on one of the rows."""

        if event.button != 3:
            # Only right clicks are processed
            return False

        x = int(event.x)
        y = int(event.y)

        pth = treeview.get_path_at_pos(x, y)
        if not pth:
            # The click wasn't on a row
            return False

        path, col, cell_x, cell_y = pth
        treeview.grab_focus()
        treeview.set_cursor(path, col, 0)

        self.show_post_popup(treeview, event)
        return True

    def show_post_popup(self, treeview, event, user_data=None):
        """Shows the popup context menu in the treeview"""

        cursor = treeview.get_cursor()
        if not cursor:
            return

        path = cursor[0]
        row_iter = self.grid_store.get_iter(path)

        popup_menu = gtk.Menu()
        popup_menu.set_screen(self.window.get_screen())

        # An open submenu with various choices underneath
        open_menu_items = []

        tweet = self.grid_store.get_value(row_iter, Columns.ALL_DATA)

        urls = url_re.findall(tweet['text'])
        for url in urls:
            if len(url) > 20:
                item_name = url[:20] + '...'
            else:
                item_name = url
            item = gtk.MenuItem(item_name)
            item.connect('activate', self.open_url, url)
            open_menu_items.append(item)

        if tweet['in_reply_to_status_id']:
            # I wish twitter made it easy to construct target url
            # without having to make another API call
            reply_to = re.search(r'@(?P<user>\w+)', tweet['text'])
            if reply_to:
                url = 'http://twitter.com/%s/statuses/%s' % (
                            reply_to.group('user'),
                            tweet['in_reply_to_status_id'])
                item = gtk.MenuItem('In reply to')
                item.connect('activate', self.open_url, url)
                open_menu_items.append(item)

        item = gtk.MenuItem('This tweet')
        username = self.grid_store.get_value(row_iter, Columns.USERNAME)
        tweet_id = self.grid_store.get_value(row_iter, Columns.ID)
        url = 'http://twitter.com/%s/statuses/%s/' % (username, tweet_id)
        item.connect('activate', self.open_url, url)
        open_menu_items.append(item)

        open_menu = gtk.Menu()
        for item in open_menu_items:
            open_menu.append(item)

        open_item = gtk.MenuItem("Open")
        open_item.set_submenu(open_menu)
        popup_menu.append(open_item)

        # Reply, only if it's not yourself
        item = gtk.MenuItem("Reply")
        item.connect('activate', self.reply_tweet, "Reply")
        if username == self.username_field.get_text():
            item.set_property('sensitive', False)
        popup_menu.append(item)

        # Retweet, only if it's not yourself
        item = gtk.MenuItem("Retweet")
        item.connect('activate', self.retweet, "Retweet")
        if username == self.username_field.get_text():
            item.set_property('sensitive', False)
        popup_menu.append(item)

        item = gtk.MenuItem("Delete")
        item.connect('activate', self.delete_tweet, "Delete")
        if username != self.username_field.get_text():
            item.set_property('sensitive', False)

        popup_menu.append(item)

        popup_menu.show_all()

        if event:
            b = event.button
            t = event.time
        else:
            b = 1
            t = 0

        popup_menu.popup(None, None, None, b, t)

        return True

    # action callbacks
    # (yes, settings should be here, but there are more settings-related
    # callbacks, so let's keep them together somewhere else)

    def open_url(self, source, url):
        """Simply opens specified url in new browser tab. We need source
        parameter so that this function can be used as an event callback"""

        self.log.debug('opening url: %s' % url)
        import webbrowser
        webbrowser.open_new_tab(url)
        self.window.set_focus(self.update_text)

    def refresh(self, widget, notify=True):
        """Update the list of twits."""

        if self.last_update:
            self.statusbar.pop(self.statusbar_context)
        self.last_update = datetime.datetime.now()

        self.log.debug('Updating list of tweets...')
        self.statusbar.push(self.statusbar_context,
                'Updating list of tweets...')

        self.twitter.friends_timeline(self.post_refresh, notify=notify)

        return True     # required by gobject.timeout_add

    def post_refresh(self, data, error, notify):
        """Function called when the system retrieves the list of new
        tweets."""

        self.log.debug('Data: %s' % (str(data)))

        if error == 401:
            # Not authorized, popup the <XXX: what?>
            gtk.gdk.threads_enter()
            error_dialog = gtk.MessageDialog(parent=self.window,
                    type=gtk.MESSAGE_ERROR,
                    message_format='Autorization error, check your login ' \
                            'information in the prefrences',
                    buttons=gtk.BUTTONS_OK)
            error_dialog.connect("response", lambda *a:
                    error_dialog.destroy())
            error_dialog.run()
            gtk.gdk.threads_leave()
            return

        if not data:
            gtk.gdk.threads_enter()
            self.statusbar.pop(self.statusbar_context)
            self.show_last_update()
            self.log.debug('No new data')
            gtk.gdk.threads_leave()
            return

        known_tweets = [row[Columns.ID] for row in self.grid_store]
        need_notify = False
        new_tweets = 0
        new_tweets_list = []

        for tweet in data:
            id = tweet['id']
            if str(id) in known_tweets:
                self.log.debug('Tweet %s is already in the list' % (id))
                continue

            created_at = tweet['created_at']
            display_name = tweet['user']['name']
            username = tweet['user']['screen_name']
            user_pic = tweet['user']['profile_image_url']
            message = tweet['text']

            new_tweets_list.append((user_pic, display_name, message, username,
                id, created_at, tweet))
            self.queue_pic(user_pic)

            self.log.debug('New tweet with id %s from %s' % (id, username))
            if not username == self.username_field.get_text():
                # we don't want to be notified about tweets from ourselves,
                # but from everyone else it is fine.
                new_tweets += 1

        # add the new tweets in the store
        gtk.gdk.threads_enter()
        for data in new_tweets_list:
            self.grid_store.append(data)

        self.statusbar.pop(self.statusbar_context)

        # there is new stuff, so we move to the top

        p = self.grid_store.get_path(self.grid_store.get_iter_first())
        self.grid.scroll_to_cell(p)
        self.show_last_update()
        self.log.debug('Tweets updated')
        gtk.gdk.threads_leave()

        if new_tweets and notify:
            self.unread_tweets += new_tweets
            self.notify(new_tweets)

        self.refresh_rate_limit()
        self.prune_grid_store()

    # ------------------------------------------------------------
    # Helper functions
    # ------------------------------------------------------------

    def clear_list(self):
        """Clear the list, so we can add more items."""

        self.grid_store.clear()

        return

    def save_interface_prefs(self):
        """Using the save callback, save all this interface preferences."""

        self.prefs['refresh_interval'] = \
                self.refresh_interval_field.get_value_as_int()

        x, y = self.window.get_position()
        self.prefs['position_x'] = x
        self.prefs['position_y'] = y

        self.save_callback(self.username_field.get_text(),
                self.password_field.get_text(),
                self.https_field.get_active(),
                namespace, self.prefs)

        return

    def refresh_rate_limit(self):
        """Request the rate limit and check if we are doing okay."""
        self.twitter.rate_limit_status(self.post_refresh_rate_limit)
        return

    def post_refresh_rate_limit(self, data, error):
        """Callback for the refresh_rate_limit."""
        if error or not data:
            self.log.error('Error fetching rate limit')
            return

        # Check if we are running low on our limit
        reset_time = datetime.datetime.fromtimestamp(
                        int(data['reset_time_in_seconds'])
                        )

        if reset_time < datetime.datetime.now():
            # Clock differences can cause this
            return

        time_delta = reset_time - datetime.datetime.now()
        mins_till_reset = time_delta.seconds/60 # Good enough!
        needed_hits = mins_till_reset/self.prefs['refresh_interval']
        remaining_hits = int(data['remaining_hits'])
        
        if needed_hits > remaining_hits:
            gtk.gdk.threads_enter()
            error_dialog = gtk.MessageDialog(parent=self.window,
                    type=gtk.MESSAGE_WARNING,
                    flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                    message_format='Refresh rate too high',
                    buttons=gtk.BUTTONS_OK)
            error_dialog.format_secondary_text(
                    "You have only %d twitter requests left until your " \
                    "request count is reset in %d minutes. But at your " \
                    "current refresh rate (every %d minutes), you will " \
                    "exhaust your limit within %d minutes. You should " \
                    "consider increasing the refresh interval in Mitter's " \
                    "Settings dialog." % (remaining_hits, mins_till_reset, 
                        self.prefs['refresh_interval'], 
                        remaining_hits * self.prefs['refresh_interval'] )
                    )
            error_dialog.connect("response", lambda *a:
                    error_dialog.destroy())
            error_dialog.run()
            gtk.gdk.threads_leave()

    def show_last_update(self):
        """Add the last update time in the status bar."""

        last_update = self.last_update.strftime('%H:%M')
        next_update = (self.last_update +
                datetime.timedelta(minutes=self.prefs[
                    'refresh_interval'])).strftime('%H:%M')

        message = 'Last update %s, next update %s' % (last_update,
                next_update)
        self.statusbar.push(self.statusbar_context, message)
        return

    def queue_pic(self, pic):
        """Check if the pic is in the queue or already downloaded. If it is
        not in any of those, add it to the download queue."""
        if pic in self.user_pics:
            return

        if pic in self.pic_queue:
            return

        self.pic_queue.add(pic)
        self.twitter.download(pic, self.post_pic_download, id=pic)
        return

    def post_pic_download(self, data, error, id):
        """Function called once we downloaded the user pic."""

        self.log.debug('Received pic %s' % (id))

        if error or not data:
            self.log.debug('Error with the pic, not loading')
            return

        loader = gtk.gdk.PixbufLoader()
        #must set size before write
        loader.set_size(48,48)
        loader.write(data)
        loader.close()

        user_pic = loader.get_pixbuf()
        user_pic  = user_pic.scale_simple(48, 48, gtk.gdk.INTERP_BILINEAR)
        self.user_pics[id] = user_pic
        self.pic_queue.discard(id)

        # finally, request the grid to redraw itself
        gtk.gdk.threads_enter()
        self.grid.queue_draw()
        gtk.gdk.threads_leave()

        return

    # ------------------------------------------------------------
    # Required functions for all interfaces
    # ------------------------------------------------------------

    def __call__(self):
        """Call function; displays the interface. This method should appear on
        every interface."""

        self.window.show_all()
        if not self.twitter.username or not self.twitter.password:
            self.settings_window.show()
        else:
            self.refresh(None, False)   # do not notify if there are new tweets
            self.update_friends_list()

        # gobject.idle_add(self.update_friends_list)
        # gobject.idle_add(self.prune_grid_store)

        gtk.main()
