import random
import asyncio

from .utils import chunk


class AsyncRequest:
    def __init__(
            self, paragraphs, translation, process_translation):
        self.paragraphs = paragraphs
        self.translation = translation
        self.process_translation = process_translation

        self.tasks = []

    async def create_worker(self, group):
        count = 0
        total = len(group)
        for paragraph in group:
            if self.translation.is_cancelled():
                return
            count += 1
            self.process_translation(paragraph)
            if self.translation.need_sleep and count < total:
                await asyncio.sleep(
                    random.randint(0, self.translation.request_interval))

    async def create_tasks(self):
        groups = chunk(self.paragraphs, self.translation.concurrency_limit)
        for group in groups:
            worker = self.create_worker(group)
            task = asyncio.create_task(worker)
            self.tasks.append(task)
        await asyncio.gather(*self.tasks)

    def run(self):
        asyncio.run(self.create_tasks())
