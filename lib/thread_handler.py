import time
import traceback
from threading import Thread

from .exception import TranslationCanceled


try:
    import queue
except ImportError:
    import Queue as queue


class ThreadHandler:
    def __init__(self, paragraphs, concurrency_limit, translate_paragraph,
                 process_translation, request_interval):
        self.queue = queue.Queue()
        for paragraph in paragraphs:
            self.queue.put_nowait(paragraph)
        self.done_queue = queue.Queue()

        self.concurrency_limit = concurrency_limit or 10  # 0 or 10
        self.translate_paragraph = translate_paragraph
        self.process_translation = process_translation
        self.request_interval = request_interval

    def translation_thread(self):
        while not self.queue.empty():
            try:
                paragraph = self.queue.get_nowait()
                self.translate_paragraph(paragraph)
                paragraph.error = None
                if self.queue.qsize() > 0 and not paragraph.is_cache:
                    time.sleep(self.request_interval)
                self.done_queue.put(paragraph)
                self.queue.task_done()
            except queue.Empty:
                break
            except TranslationCanceled:
                self.queue.task_done()
                while not self.queue.empty():
                    self.queue.get_nowait()
                    self.queue.task_done()
                while not self.done_queue.empty():
                    self.done_queue.get_nowait()
                    self.done_queue.task_done()
                break
            except Exception:
                paragraph.error = traceback.format_exc(chain=False).strip()
                self.done_queue.put(paragraph)
                self.queue.task_done()

    def processing_thread(self):
        while True:
            paragraph = self.done_queue.get()
            if paragraph is None:
                break
            self.process_translation(paragraph)
            self.done_queue.task_done()

    def create_threads(self):
        threads = []
        for _ in range(self.concurrency_limit):
            thread = Thread(target=self.translation_thread)
            thread.start()
            threads.append(thread)
        return threads

    def handle(self):
        Thread(target=self.processing_thread).start()
        for thread in self.create_threads():
            thread.join()
        self.done_queue.put(None)
