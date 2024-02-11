import logging
logging.basicConfig(level=logging.INFO)
import os
import re
import time
from queue import Queue
from threading import Thread
import werkzeug
werkzeug.cached_property = werkzeug.utils.cached_property
from robobrowser import RoboBrowser
from requests import Session
from requests.exceptions import Timeout
from unidecode import unidecode

class Downloader():
    def __init__(self, proxy=None, worker_num=0):
        self.worker_num = worker_num
        session         = Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
        if proxy is not None:
            session.proxies = {'http': proxy, 'https': proxy}
        self.browser = RoboBrowser(history=True, parser='html.parser', session=session)


    def get_author_url(self, author):
        ''' Get author url from input given '''
        author_name = author.replace(" ", "-").lower()
        author_url  = f'https://ww3.lectulandia.com/autor/{author_name}'
        return author_url


    def get_books_titles_from_author_url(self, author_url):
        self.browser.open(author_url)
        books_titles_from_author = [
            f"{book['title']}"
            for book in self.browser.find_all("a", class_="title")]
        logging.info(f'Number of titles retrieved: {len(books_titles_from_author)}')
        return books_titles_from_author


    def get_urls_from_author_url(self, author_url, urls_from_author=None):
        # TODO: recopilar TODAS las paginas, no solo la primera
        if urls_from_author is None:
            urls_from_author = []

        self.browser.open(author_url)
        new_urls = [
            f"https://ww3.lectulandia.com{book['href']}"
            for book in self.browser.find_all("a", class_="card-click-target")]
        urls_from_author.extend(new_urls)

        next_page_link = self.browser.find("a", class_="next page-numbers")
        if next_page_link:
            next_page_url = f"https://ww3.lectulandia.com{next_page_link['href']}"
            self.get_urls_from_author_url(next_page_url, urls_from_author)
            #next_page_urls = self.get_urls_from_author_url(next_page_url)  # Recursive call

        return urls_from_author


    def get_download_link(self, book_url):
        self.browser.open(book_url)
        for link in self.browser.find_all("a"):
            if "download.php?t=1" in str(link):
                return f"https://www.lectulandia.com{link['href']}"


    def get_batch_download_links(self, urls_from_author):
        download_links = [self.get_download_link(book_url) for book_url in urls_from_author]
        return download_links


    def download_book(self, download_url, author, timeout=180):
        # Replace with library folder
        library_folder = "F:\Calibre Library"
        author_folder  = os.path.join(library_folder, author)
        try:
            if not os.path.exists(author_folder):
                os.makedirs(author_folder)

            logging.info(f'Downloading book from {download_url}')
            self.browser.open(download_url)
            pattern = re.compile("var linkCode = \"(.*?)\";")
            section = pattern.findall(str(self.browser.parsed))
            ant_url = f'https://www.antupload.com/file/{section[0]}'
            self.browser.open(ant_url)

            filename = self.browser.find(
                "div", id="fileDescription").find_all("p")[1].text.replace(
                    "Name: ", "")
            logging.info(f"Filename: {filename}")
            size = self.browser.find(
                "div", id="fileDescription").find_all("p")[2].text
            file_url = self.browser.find("a", id="downloadB")
            logging.info(size)
            time.sleep(2)

            # Check if the file already exists in the target directory
            file_path = os.path.join(author_folder, filename)
            if os.path.exists(file_path):
                logging.info(f'File already exists: {file_path}')
                return None

            self.browser.follow_link(file_url, timeout=timeout)

            with open(file_path, "wb") as epub_file:
                epub_file.write(self.browser.response.content)
                logging.info(f'File has been saved to: {epub_file.name}')
                return filename, size

        except Timeout:
            logging.error(f'Timeout error during download. URL: {download_url}')
            return None

        except Exception as e:
            logging.error(f'Error downloading book: {str(e)}')
            return None

    def batch_download_books(self, urls_from_author, author):
        for url in urls_from_author:
            self.download_book(url, author)
            #time.sleep(1)


    def get_book_page_list(self, page:int):
        self.browser.open(f'https://ww3.lectulandia.com/book/page/{page}/')
        return [
            f"https://ww3.lectulandia.com{book['href']}"
            for book in self.browser.find_all("a", class_="card-click-target")
        ]


    def download_full_page(self, page:int):
        logging.info(f"Downloading page: {page} ")
        try:
            books = self.get_book_page_list(page)
            for book in books:
                time.sleep(1)
                download_url = self.get_download_link(book)
                logging.info(f"Worker: {self.worker_num} on page: {page}", self.download_book(download_url))
        except Exception as e:
            logging.error(f'Error downloading full page: {str(e)}')


class Worker(Thread):
    def __init__(self, queue, worker_number, proxy=None):
        Thread.__init__(self)
        self.queue      = queue
        self.downloader = Downloader(proxy)
        self.worker_num = worker_number

    def run(self):
        while True:
            page = self.queue.get()
            try:
                logging.info(f"Worker: {self.worker_num} downloading page: {page}")
                self.downloader.download_full_page(page)
            except Exception as e:
                logging.error(f'Error in worker {self.worker_num} while processing page {page}: {str(e)}')
            finally:
                self.queue.task_done()


def main():
    pages   = [x + 1 for x in range(8)]
    proxies = None #[None, "https://188.168.75.254:56899"]
    queue   = Queue()

    # Creating workers
    workers = []
    for x in range(2):
        worker = Worker(queue, x, proxies[x])
        worker.daemon = True
        worker.start()
        workers.append(worker)

    # Enqueueing pages
    for page in pages:
        queue.put(page)

    # Waiting for all tasks to finish
    queue.join()

    # Waiting for all workers to finish
    for worker in workers:
        worker.join()
