from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock
from kivy.core.window import Window
from processes.thumbnail import ThumbnailGenerator
from common import mk_logger, posix_path, pure_windows_path, thumb_dir, cache_path
from shutil import copyfile
from os import path, remove, rename

logger = mk_logger(__name__)
ex_log = mk_logger(name=f'{__name__}-EX',
                   level=40,
                   _format='[%(levelname)-8s] [%(asctime)s] [%(name)s] [%(funcName)s] [%(lineno)d] [%(message)s]')
ex_log = ex_log.exception


class ThumbnailPopup(BoxLayout):
    def __init__(self, originator, destination, filename, sftp):
        super().__init__()
        self.originator = originator
        self.destination = destination
        self.filename = filename
        self.sftp = sftp
        self.pic_name = None
        Window.bind(on_dropfile=self.thumbnail_drop)

    def thumbnail_drop(self, _, src_path):
        src_path = src_path.decode(encoding='UTF-8', errors='strict')
        print('THUMBNAIL DROP', src_path)
        print('     SRC', src_path)
        print('     DST', self.destination)
        print('     FILENAME', self.filename)
        self.thumbnail = path.split(src_path)[1]
        self.pic_name = f'{self.filename}.jpg'
        cache_pic = pure_windows_path(cache_path, self.thumbnail)
        print('     CACHE PIC', self.filename, cache_pic)
        try:
            if path.exists(cache_pic):
                remove(cache_pic)
            copyfile(src_path, cache_pic)

        except Exception as ex:
            self.popup.title = f'Failed to generate thumbnail {ex}'
            print('FAILED TO MOVE PIC', ex)
            return

        th = ThumbnailGenerator(src_path=cache_pic, dst_path='')
        th.start()
        th.join()
        if th.ok:
            self.popup.title = 'Thumbnail generated'
            print('Thumbnail Generated')
            cache_pic = pure_windows_path(cache_path, self.destination.strip('/'), thumb_dir, self.pic_name)

            try:
                if path.exists(cache_pic):
                    remove(cache_pic)
                copyfile(th.thumb_path, cache_pic)

                print('     SRC_PATH', cache_pic)
                print('     DST_PATH', posix_path(self.destination, thumb_dir, self.pic_name))
                self.sftp.put(cache_pic, posix_path(self.destination, thumb_dir, self.pic_name), preserve_mtime=True)
            except Exception as ex:
                ex_log(f'Failed to upload thumbnail for {self.filename} {ex}')
            else:
                self.popup.title = 'Thumbnail uploaded succesfully'
                self.originator.bind_external_drop()
                def dismiss_popup(_):
                    self.popup.dismiss()
                    self.originator.refresh_thumbnail(self.filename)
                Clock.schedule_once(dismiss_popup, .8)
                Window.unbind(on_dropfile=self.thumbnail_drop)
        else:
            self.popup.title = 'Failed to upload thumbnail'
