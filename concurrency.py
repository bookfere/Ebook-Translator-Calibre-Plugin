import asyncio

from calibre_plugins.ebook_translator.utils import chunk


def async_(concurrency, original_group, translate, progress, callback):
    async def worker(group, progress):
        results = []
        for identity, original in group:
            progress()
            results.append(translate(identity, original))
        return results

    async def main():
        tasks = []
        groups = chunk(original_group, concurrency)
        for group in groups:
            task = worker(group, progress)
            tasks.append(asyncio.create_task(task))
        for results in await asyncio.gather(*tasks):
            callback(results)

    asyncio.run(main())
