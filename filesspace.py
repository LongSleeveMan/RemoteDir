from kivy.uix.stacklayout import StackLayout
from kivy.graphics import Color, Rectangle
from kivy.properties import ObjectProperty
from kivy.core.window import Window
from common import confirm_popup, menu_popup, posix_path, is_file, mk_logger, thumbnail_popup, hidden_files
import win32clipboard as clipboard
from filetile import FileTile
from filedetails import FileDetails
import os
import copy
from functools import partial

logger = mk_logger(__name__)
ex_log = mk_logger(name=f'{__name__}-EX',
                   level=40,
                   _format='[%(levelname)-8s] [%(asctime)s] [%(name)s] [%(funcName)s] [%(lineno)d] [%(message)s]')
ex_log = ex_log.exception


class FilesSpace(StackLayout):
    originator = ObjectProperty()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind_external_drop()
        Window.bind(mouse_pos=self.on_mouse_move)
        self._keyboard = Window.request_keyboard(self.key_press, self)
        self._keyboard.bind(on_key_down=self.key_press)
        self._keyboard.bind(on_key_up=self.key_up)
        Window.bind(on_cursor_leave=partial(self.on_mouse_move, None, (0, 0)))
        self.marked_files = set()
        self.copied_files = []
        self.pressed_key = ''
        self.sort_by = 'filename'
        self.reverse = False
        self.moving = False
        self.icon = FileTile
        self.rectangle = None
        self.mark_rectangle = None
        self.p_touch = None
        self.touched_file = None
        self.mark = None
        self.attrs_list = None
        self.touch = None
        self.thumb = True

    def get_file_index(self, file):
        return self.children.index(file)

    def fill(self, attrs_list):
        self.clear_widgets()
        self.attrs_list = attrs_list
        for attrs in self.attrs_list:
            self.add_icon(attrs)

    def add_icon(self, attrs, new_dir=False):
        """New dir means the dir was created remotely"""
        if attrs.filename in hidden_files:
            return
        icon = self.icon.from_attrs(attrs=attrs, space=self)
        if new_dir:
            icon.enable_rename()

    def add_file(self, attrs):
        # in case file was overwritten during upload
        # find the file and remove it from view.
        for file in self.children:
            if file.filename == attrs.filename:
                self.remove_widget(file)
                self.attrs_list.remove(file.attrs)
                break
        self.attrs_list.append(attrs)
        self.add_icon(attrs)

    def refresh_thumbnail(self, name):
        for file in self.children:
            if file.filename == name:
                file.set_thumbnail()
                break

    def rename_file(self, old, new, file):
        self.originator.rename_file(old=old, new=new, file=file)

    def remove_file(self, file):
        """
        Removes icon from filespace.
        Icon can be given as filename (str) or object as instance of FileTile, FileDetails etc.
        """
        if type(file) == str:
            for _file in self.children:
                if file == _file.filename:
                    file = _file
                    break
            else:
                return

        for i, attrs in enumerate(self.attrs_list):
            if file.filename == attrs.filename:
                self.attrs_list.pop(i)

        self.remove_widget(file)

    def sort_files(self, sort_by=None):

        if sort_by == 'Name':
            self.sort_by = 'filename'
        elif sort_by == 'Date added':
            self.sort_by = 'st_atime'
        elif sort_by == 'Date modified':
            self.sort_by = 'st_mtime'
        elif sort_by == 'Size':
            self.sort_by = 'st_size'

        self.attrs_list.sort(key=lambda x: (x.__dict__[self.sort_by]), reverse=self.reverse)
        self.fill(self.attrs_list)

    def file_size(self, size):
        for file in self.children:
            file.resize(size)

        self.do_layout()

    # mouse behavior [on_touch_down, on_touch_up, on_touch_move]
    def on_mouse_move(self, *args):
        mouse_pos = args[1]

        if not self.originator.mouse_locked:
            for child in self.children:
                
                if child.focus:
                    child.background_color = child.focused_color

                elif child.collide_point(*child.to_widget(*mouse_pos))\
                        and not (is_file(child.attrs) and self.moving):
                    # do not change background color of icons when moving files and mouse dosesn't point directory
                    child.background_color = child.active_color

                else:
                    child.background_color = child.unactive_color

    def on_touch_down(self, touch):
        self.touch = touch
        self.touched_file = self.find_touched_file(touch.pos)

        if not self.touched_file:
            self.marked_files.clear()
            self.on_popup_dismiss()
            for file in self.children:
                file.focus = False
            if touch.button == 'right':
                self.show_menu()

        else:
            # touch.is_double_tap returns True when key is pressed. Even if it is not double tapped.
            if touch.is_double_tap and not self.pressed_key:

                if self.touched_file.file_type == 'dir':
                    self.open_file(self.touched_file)

            elif 'ctrl' in self.pressed_key:

                self.touched_file.focus = True

            elif 'shift' in self.pressed_key:

                indexes = [self.get_file_index(file) for file in self.marked_files]
                current_index = self.get_file_index(self.touched_file)
                _min = min(indexes)
                _max = max(indexes)

                if current_index < _min:
                    _range = (current_index, _max)

                elif _min < current_index < _max:
                    _range = (current_index, _max)

                else:
                    _range = (_max, current_index)

                for i, file in enumerate(self.children):
                    if _range[0] <= i <= _range[1]:
                        file.focus = True
                    else:
                        file.focus = False

            elif not self.pressed_key:
                if self.touched_file not in self.marked_files:
                    self.marked_files.clear()
                    self.marked_files.add(self.touched_file)

                if len(self.marked_files) == 1:
                    for file in self.children:
                        if file != self.touched_file:
                            file.focus = False

                if touch.button == 'right':
                    self.show_menu()

        self.p_touch = [touch.x, touch.y]
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):

        if touch.is_mouse_scrolling:
            return super().on_touch_up(touch)
        self.touched_file = self.find_touched_file(touch.pos)
        if 'ctrl' in self.pressed_key:
            pass
        elif 'shift' in self.pressed_key:
            pass

        elif self.touched_file and len(self.marked_files) > 1:
            # manage group of marked files
            if not self.marking and not self.moving:
                # unmark files
                self.unfocus_files([self.touched_file])
            elif not self.moving:
                self.unfocus_files([self.touched_file])

        try:
            self.remove_mark_area()
        finally:
            self.marked_files.clear()
            self.find_marked_files()
            self.moving = False

            return super().on_touch_up(touch)

    def on_touch_move(self, touch):
        if self.originator.mouse_locked:
            return super().on_touch_move(touch)

        if not self.marked_files:

            if not self.marking() and not touch.is_mouse_scrolling:
                # start to draw rectangle if no file is marked
                self.mark = self.mark_area(touch.pos)
            elif self.marking():
                # draw rectangle if already started
                self.mark(touch.pos)

        else:
            # move marked files
            # Calculating my own dx and dy because cant use touch.dx and touch.dy with scrolling.
            # Catching previous touch in self.touch because touch.ppos accualy returns something
            # different than pos of previously recived touch.
            dx = touch.x - self.p_touch[0]
            dy = touch.y - self.p_touch[1]
            self.move_files(dx, dy)
            self.p_touch = [touch.x, touch.y]

        return super().on_touch_move(touch)

    def show_menu(self):

        if self.touched_file:
            self.find_marked_files()

            if len(self.marked_files) == 1:
                buttons = ['Rename', 'Download', 'Open', 'Delete']
                if self.thumb:
                    buttons.append('Add Thumbnail')

            else:
                buttons = ['Delete', 'Download']

        else:
            buttons = ['Make dir', 'Refresh']

        menu_popup(originator=self,
                   buttons=buttons,
                   callback=self.menu,
                   mouse_pos=self.to_window(*self.touch.pos))
        self.on_popup()

    def menu(self, option):
        if option == 'Refresh':
            self.originator.list_dir()
        elif option == 'Delete':
            self.remove_popup()
        elif option == 'Open':
            self.open_file(self.touched_file)
        elif option == 'Download':
            self.download(self.touched_file)
        elif option == 'Make dir':
            self.make_dir()
        elif option == 'Rename':

            self.touched_file.enable_rename()
        elif option == 'Add Thumbnail':
            self.unbind_external_drop()
            thumbnail_popup(originator=self,
                            destination=self.originator.get_current_path(),
                            filename=self.touched_file.filename,
                            sftp=self.originator.sftp)


    def bind_external_drop(self):
        Window.bind(on_dropfile=self.external_dropfile)

    def unbind_external_drop(self):
        Window.unbind(on_dropfile=self.external_dropfile)

    def make_dir(self):
        i = 0
        for child in self.children:
            print('NAME', child.filename)
            if 'New dir' in child.filename:
                print('     New dir in')
                i += 1
        if i:
            name = f'New dir {i}'
        else:
            name = 'New dir'

        self.originator.make_dir(name)

    def marking(self):
        return self.mark is not None

    def download(self, file):
        self.originator.download(file)

    def find_touched_file(self, pos):
        """Looks for files that was marked on touch down or on touch move"""

        for file in self.children:
            if file.collide_point(*pos):
                return file
        else:
            return None

    def focus_marked_files(self):
        """Focusing widgets colliding with drawn rectangle"""
        for file in self.children:
            if file.collide_rectangle(*self.mark_rectangle):
                file.focus = True
            else:
                file.focus = False

    def find_marked_files(self):
        """
        Lokiing for a focused file and adding to marked_files
        """

        for file in self.children:
            if file.focus:
                self.marked_files.add(file)

    def move_files(self, dx, dy):
        self.moving = True
        for file in self.marked_files:
            file.set_pos(dx, dy)

    def external_dropfile(self, window, localpath):
        """
        When file is dropped or pasted from Windows
        """

        destination = None
        if window:
            touched = self.find_touched_file(self.to_widget(window._mouse_x, window.height - window._mouse_y))

            if touched and touched.file_type == 'dir':
                destination = touched.filename
        self.originator.external_dropfile(localpath, destination)

    def internal_file_drop(self, file):
        """Called from FileBox when it detects widget collision"""
        for mfile in self.marked_files:
            old = mfile.filename
            new = posix_path(file.filename, mfile.filename)
            self.originator.rename_file(old, new, mfile, drop=True)

    def unfocus_files(self, files=None):
        """
        Unfocus files from self.children in they are not in files list
        """
        if files:
            for file in self.children:
                if file not in files:
                    file.focus = False
        files.clear()

    def mark_area(self, pos):
        with self.canvas:
            Color(0, 0, 0, .2)
            self.rectangle = Rectangle(pos=pos, size=(0, 0))
            self.mark_rectangle = [pos[0], pos[1], 0, 0]

        def mark_files(end):
            width = end[0] - pos[0]
            heigth = end[1] - pos[1]
            self.mark_rectangle[2] = end[0]
            self.mark_rectangle[3] = end[1]
            self.rectangle.size = (width, heigth)
            self.focus_marked_files()

        return mark_files

    def mark_all_files(self):
        for file in self.children:
            file.focus = True
            self.marked_files.add(file)

    def remove_mark_area(self):
        self.rectangle.size = (0, 0)
        self.mark = None
    # end files management

    # keyboard management [key_up, key_press]
    def key_up(self, *args):
        self.pressed_key = ''

    def key_press(self, *args):
        # args when keyboard key pressed [keyboard, keycode, text, modifiers]
        if len(args) == 4:
            self.pressed_key = args[1][1]
            modifiers = args[3]
            # noinspection PyBroadException
            try:

                if self.pressed_key == 'delete':
                    self.find_marked_files()
                    if self.marked_files:
                        self.remove_popup()
                elif self.pressed_key == 'a' and 'ctrl' in modifiers:
                    self.mark_all_files()

                elif self.pressed_key == 'c' and 'ctrl' in modifiers:
                    self.copy_files()

                elif self.pressed_key == 'v' and 'ctrl' in modifiers:
                    self.paste_files()

                elif self.pressed_key == 'n' and 'ctrl' in modifiers and 'shift' in modifiers:
                    self.make_dir()

            except Exception:
                pass

    # end keyboard management
    def copy_files(self):
        self.copied_files.clear()
        wd = self.originator.get_cwd()
        for file in self.marked_files:
            self.copied_files.append(os.path.join(wd, file.filename))

    def paste_files(self):
        clipboard.OpenClipboard()
        files = ()
        if clipboard.IsClipboardFormatAvailable(clipboard.CF_HDROP):
            files = copy.deepcopy(clipboard.GetClipboardData(clipboard.CF_HDROP))

        clipboard.EmptyClipboard()
        clipboard.CloseClipboard()

        for file in files:
            file = bytes(file, 'utf-8')
            self.external_dropfile(None, file)

    def open_file(self, file):
        self.originator.open_file(file)

    def on_popup(self):
        self.originator.mouse_locked = True

    def on_popup_dismiss(self):
        self.originator.mouse_locked = False

    def remove_popup(self):
        self.originator.on_popup()
        text = 'files' if len(self.marked_files) > 1 else 'file'
        confirm_popup(callback=self.remove,
                      text=f'Are you sure you want to remove this {text} permanently?',
                      movable=True)

        self.on_popup()

    def view_menu(self, icon):
        if icon == 'Tiles':
            self.icon = FileTile
        elif icon == 'Details':
            self.icon = FileDetails

        self.sort_files()

    def remove(self, popup, _, answer):
        if answer == 'yes':
            self.find_marked_files()
            for file in self.marked_files:
                self.originator.remove(file)

        self.on_popup_dismiss()
        popup.dismiss()
