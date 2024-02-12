import logging
import os
import re
import time
import werkzeug
werkzeug.cached_property = werkzeug.utils.cached_property
from robobrowser import RoboBrowser
import requests
from unidecode import unidecode
import random

# Set logging to log into an external file as well as stream in the console
import logging
logging.basicConfig(filename='Downloader_log.txt',
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
# Create a StreamHandler to print log messages to the console
console_handler   = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Add the StreamHandler to the logger
logging.getLogger().addHandler(console_handler)

class Downloader():
    def __init__(self, proxy=None, library_folder=r'F:\Calibre Library'):
        self.library_folder = library_folder
        # Header rotation
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/91.0.864.37",
        ]
        self.current_user_agent = random.choice(self.user_agents)
        session = requests.Session()
        session.headers.update({
            'User-Agent': self.current_user_agent
        })
        if proxy is not None:
            session.proxies = {'http': proxy, 'https': proxy}
        self.browser = RoboBrowser(history=True, parser='html.parser', session=session)


    def rotate_user_agent(self):
        ''' Rotate to the next User-Agent in the list '''
        self.current_user_agent = random.choice(self.user_agents)


    def get_author_url(self, author:str):
        ''' Get author url from author name given as input '''
        # Input validation
        if not author or not isinstance(author, str):
            raise ValueError("Author name must be a non-empty string")
        # Check if base url is active
        base_url = 'https://ww3.lectulandia.com/'
        response = requests.head(base_url)
        if response.status_code != 200:
            raise requests.ConnectionError("Base URL is not active. Please set a different base URL")
        # Create author url
        author_name = author.replace(" ", "-").lower()
        author_url  = f'{base_url}autor/{author_name}'
        return author_url


    def get_books_titles_from_author_url(self, author_url:str):
        ''' Get book titles from a given author url '''
        self.browser.open(author_url)
        books_titles_from_author = [
            f"{book['title']}"
            for book in self.browser.find_all("a", class_="title")]
        logging.info(f'Number of titles retrieved: {len(books_titles_from_author)}')
        # Rotate User-Agent after making the request
        self.rotate_user_agent()
        return books_titles_from_author


    def get_urls_from_author_url(self, author_url:str, urls_from_author=None):
        ''' Get list of book links from a given author'''
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
            # Recursive call as long as there is a "Siguiente" button
            self.get_urls_from_author_url(next_page_url, urls_from_author)

        # Rotate User-Agent after making the request
        self.rotate_user_agent()
        if not urls_from_author:
            raise Exception("There are no URLs for this author! Try a different one")
        return urls_from_author


    def get_download_link(self, book_url:str):
        ''' Turn book link into a download url '''
        self.browser.open(book_url)
        for link in self.browser.find_all("a"):
            if "download.php?t=1" in str(link):
                return f"https://www.lectulandia.com{link['href']}"


    def get_batch_download_links(self, urls_from_author:list):
        ''' Get whole list of links to download from a given author '''
        download_links = [self.get_download_link(book_url) for book_url in urls_from_author]
        return download_links

    def download_book(self, download_url:str, author:str, timeout=180):
        ''' Download a book and save into local directory if not exists already '''
        library_folder = self.library_folder
        author_name    = unidecode(author.title()) # Clean format
        author_folder  = os.path.join(library_folder, author_name)
        try:
            if not os.path.exists(author_folder):
                os.makedirs(author_folder)
            logging.info(f'Downloading book from {download_url}')
            self.rotate_user_agent()  # Rotate headers before making the request
            self.browser.open(download_url)
            pattern = re.compile("var linkCode = \"(.*?)\";")
            section = pattern.findall(str(self.browser.parsed))
            ant_url = f'https://www.antupload.com/file/{section[0]}'
            logging.info(f'antupload: {ant_url}')
            self.browser.open(ant_url)
            filename = self.browser.find(
                "div", id="fileDescription").find_all("p")[1].text.replace(
                    "Name: ", "")
            logging.info(f"Filename: {filename}")
            size = self.browser.find(
                "div", id="fileDescription").find_all("p")[2].text
            file_url = self.browser.find("a", id="downloadB")
            logging.info(size)
            #logging.info(f'{file_url}')
            # Check if the file already exists in the target directory
            file_path = os.path.join(author_folder, filename)
            if os.path.exists(file_path):
                logging.info(f'File already exists: {file_path}')
                return None
            if file_url:
                self.browser.follow_link(file_url, timeout=timeout)
                with open(file_path, "wb") as epub_file:
                    epub_file.write(self.browser.response.content)
                    logging.info(f'File has been saved to: {epub_file.name}')
                    return filename, size
            else:
                logging.error(f'Error downloading book: Unable to retrieve download link')
                return None
        except requests.exceptions.Timeout:
            logging.error(f'Timeout error during download. URL: {download_url}')
            return None
        except Exception as e:
            logging.error(f'Error downloading book: {str(e)}')
            return None


    def batch_download_books(self, urls_from_author:list, author:str):
        ''' Download all book collection from a given author'''
        for url in urls_from_author:
            self.download_book(url, author)
            time.sleep(1)


    def get_book_page_list(self, page:int):
        ''' Get list of book titles from a given page number '''
        page_url = f'https://ww3.lectulandia.com/book/page/{page}/'
        self.browser.open(page_url)
        logging.info(f'Getting book page list from {page_url}')
        book_page_list = [
            f"https://ww3.lectulandia.com{book['href']}"
            for book in self.browser.find_all("a", class_="card-click-target")]
        return book_page_list


    def download_full_page(self, page:int):
        ''' Download a full page '''
        logging.info(f"Downloading page: {page} ")
        try:
            books = self.get_book_page_list(page)
            for book in books:
                time.sleep(1)
                download_url = self.get_download_link(book)
        except Exception as e:
            logging.error(f'Error downloading full page: {str(e)}')
