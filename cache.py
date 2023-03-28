import os
import shutil
import sqlite3
import os.path
import tempfile
from glob import glob


class TranslationCache:
    dir_path = os.path.join(
        tempfile.gettempdir(), 'com.bookfere.Calibre.EbookTranslator')

    def __init__(self, uid):
        self.file_path = self._path(uid)
        self.connection = sqlite3.connect(self.file_path)
        self.cursor = self.connection.cursor()
        self.cursor.execute('CREATE TABLE IF NOT EXISTS cache(md5, content)')

    def _path(self, name):
        if not os.path.exists(self.dir_path):
            os.mkdir(self.dir_path)
        return os.path.join(self.dir_path, '%s.db' % name)

    def add(self, md5, content):
        self.cursor.execute('INSERT INTO cache VALUES (?, ?)', (md5, content))
        self.connection.commit()

    def get(self, md5):
        resource = self.cursor.execute(
            'SELECT content FROM cache WHERE md5=?', (md5,))
        result = resource.fetchone()
        return result[0] if result else result

    def exists(self):
        return os.path.exists(self.file_path)

    def destroy(self):
        self.connection.close()
        os.remove(self.file_path)

    @classmethod
    def count(cls):
        total = 0
        for cache in glob(os.path.join(cls.dir_path, '*.db')):
            total += os.path.getsize(cache)
        return '%sMB' % round(float(total) / (1000 ** 2), 2)

    @classmethod
    def clean(cls):
        shutil.rmtree(cls.dir_path, ignore_errors=True)
