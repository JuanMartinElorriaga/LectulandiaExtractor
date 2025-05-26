from loguru import logger
import os
import re
from rapidfuzz import fuzz
import requests
import sys
import time
import werkzeug
werkzeug.cached_property = werkzeug.utils.cached_property
from robobrowser import RoboBrowser
from unidecode import unidecode

# Set logger to log into an external file as well as stream in the console
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time} - {level} - {message}")
logger.add("Downloader_log.txt", level="INFO", format="{time} - {level} - {message}", rotation="10 MB", compression="zip")

# Paso 1: Verificar si autor ya existe (fuzzy match en Calibre)
# Paso 2: Si no existe, crear nueva carpeta en download_folder
# Paso 3: Si existe, usar nombre existente y listar subcarpetas (libros)
# Paso 4: Para cada libro nuevo, verificar si ya fue descargado (fuzzy contra subcarpetas)
# Paso 5: Si no está, crear carpeta del libro, descargar y guardar

def clean_folder_name(name):
    """ Funcion helper para remover sufijo a las subcarpetas indexadas por Calibre """
    return re.sub(r'\s\(\d+\)$', '', name.strip())

class Downloader():
    def __init__(self, proxy:str, download_folder:str, calibre_library:str):
        self.download_folder = download_folder
        self.calibre_library = calibre_library
        session = requests.Session()
        if proxy:
            session.proxies = {'http': proxy, 'https': proxy}
        self.browser = RoboBrowser(history=True, parser='html.parser', session=session)


    def _get_existing_author_folder(self, author_name_cleaned: str) -> tuple[str, list[str]]:
        """Busca coincidencia fuzzy en Calibre; si hay match, devuelve también subcarpetas"""
        threshold       = 90
        best_match_name = None
        best_score      = 0
        subfolders      = []

        for calibre_folder in os.listdir(self.calibre_library):
            calibre_path = os.path.join(self.calibre_library, calibre_folder)
            if os.path.isdir(calibre_path):
                normalized = unidecode(calibre_folder).strip().lower()
                score = fuzz.ratio(normalized, author_name_cleaned)
                if score >= threshold and score > best_score:
                    best_match_name = calibre_folder
                    best_score = score
                    logger.info(f'Carpeta existente detectada por fuzzy match: "{calibre_folder}" (score: {score}%)')

        # Determinar carpeta final de destino
        normalized_capitalized = ' '.join(word.capitalize() for word in author_name_cleaned.split())
        final_author_folder = best_match_name if best_match_name else normalized_capitalized
        final_path = os.path.join(self.download_folder, final_author_folder)

        # Crear carpeta destino si no existe
        if not os.path.exists(final_path):
            os.makedirs(final_path)
            logger.info(f'Carpeta creada: {final_path}')
        else:
            logger.info(f'Carpeta ya existente: {final_path}')

        # Buscar subcarpetas existentes dentro de calibre_library
        calibre_author_path = os.path.join(self.calibre_library, final_author_folder)
        if os.path.exists(calibre_author_path):
            raw_subfolders = [f for f in os.listdir(calibre_author_path) if os.path.isdir(os.path.join(calibre_author_path, f))]
            subfolders = [clean_folder_name(f) for f in raw_subfolders]
        else:
            logger.info(f'No se encontró la carpeta del autor en calibre: {calibre_author_path}')

        return final_path, subfolders


    def get_author_url(self, author:str) -> str:
        ''' Get author url from author name and url '''
        # Input validation
        if not author or not isinstance(author, str):
            raise ValueError("El autor debe ser un string no nulo")

        # Check if base url is active
        base_url = 'https://ww3.lectulandia.com/'
        response = requests.head(base_url)
        if response.status_code != 200:
            raise requests.ConnectionError(f"La URL: {base_url} no se encuentra activa. Por favor, setear una diferente.")

        # Create author url
        author_name = author.replace(" ", "-").lower()
        author_url  = f'{base_url}autor/{author_name}'
        return author_url


    def get_books_titles_from_author_url(self, author_url:str) -> list:
        ''' Get book titles for a given author url '''
        self.browser.open(author_url)
        books_titles_from_author = [
            f"{book['title']}"
            for book in self.browser.find_all("a", class_="title")]
        logger.info(f'Cantidad de libros obtenidos: {len(books_titles_from_author)}')
        return books_titles_from_author


    def get_urls_from_author_url(self, author_url:str, urls_from_author:list=None) -> list:
        ''' Get list of book links for a given author'''
        if not urls_from_author:
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

        if not urls_from_author:
            raise Exception("No hay URLs para este autor! Intentar un autor distinto.")
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


    def download_cover_google_books(self, title: str, author: str, file_path: str) -> None:
            """ Descarga portada usando Google Books API según título y autor """
            try:
                query = f'intitle:"{title}"+inauthor:"{author}"'
                url = f'https://www.googleapis.com/books/v1/volumes?q={query}'

                logger.info(f"Consultando Google Books API con: {query}")
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()

                if 'items' not in data or len(data['items']) == 0:
                    logger.warning(f"No se encontraron resultados para '{title}' de '{author}'")
                    return

                volume_info = data['items'][0].get('volumeInfo', {})
                image_links = volume_info.get('imageLinks', {})
                cover_url = image_links.get('thumbnail') or image_links.get('smallThumbnail')

                if not cover_url:
                    logger.warning("No se encontró la imagen de portada en los resultados de la API.")
                    return

                if cover_url.startswith("http://"):
                    cover_url = cover_url.replace("http://", "https://")

                logger.info(f"Descargando portada desde: {cover_url}")
                img_response = requests.get(cover_url)
                img_response.raise_for_status()

                cover_path = os.path.join(os.path.dirname(file_path), "cover.jpg")
                with open(cover_path, "wb") as f:
                    f.write(img_response.content)

                logger.info(f"Portada guardada en: {cover_path}")

            except requests.RequestException as e:
                logger.warning(f"Error en la petición HTTP: {e}")
            except Exception as e:
                logger.warning(f"Error al descargar portada: {e}")


    def download_book(self, download_url: str, author: str, timeout: int = 180) -> None:
        author_name_cleaned = unidecode(author).strip().lower()
        author_folder, existing_books = self._get_existing_author_folder(author_name_cleaned)

        try:
            logger.info(f'Descargando desde: {download_url}')
            self.browser.open(download_url)
            pattern = re.compile("var linkCode = \"(.*?)\";")
            section = pattern.findall(str(self.browser.parsed))
            ant_url = f'https://www.antupload.com/file/{section[0]}'
            logger.info(f'antupload: {ant_url}')
            self.browser.open(ant_url)

            raw_filename = self.browser.find("div", id="fileDescription").find_all("p")[1].text.replace("Name: ", "")
            size = self.browser.find("div", id="fileDescription").find_all("p")[2].text

            book_name = os.path.splitext(raw_filename)[0].split(" - ")[0].strip()
            filename = f"{book_name}.epub"

            # Verificación fuzzy contra subcarpetas existentes
            threshold = 90
            book_name_cleaned = unidecode(book_name).strip().lower()
            for existing in existing_books:
                existing_cleaned = unidecode(existing).strip().lower()
                score = fuzz.ratio(existing_cleaned, book_name_cleaned)
                if score >= threshold:
                    logger.info(f'Se detectó un libro similar ya existente: "{existing}" (score: {score}%). Se omite la descarga.')
                    return None

            book_folder = os.path.join(author_folder, book_name)
            if os.path.exists(book_folder):
                logger.info(f'El libro ya existe en la carpeta destino: {book_folder}. Se omite la descarga.')
                return None
            else:
                os.makedirs(book_folder, exist_ok=True)

            file_path = os.path.join(book_folder, filename)
            file_url = self.browser.find("a", id="downloadB")
            logger.info(f"Nombre de archivo: {filename}")
            logger.info(f"Tamaño de archivo: {size}")

            if file_url:
                time.sleep(1)
                self.browser.follow_link(file_url, timeout=timeout)
                with open(file_path, "wb") as epub_file:
                    epub_file.write(self.browser.response.content)
                    logger.info(f'El archivo ha sido descargado en: {epub_file.name}')
                    self.download_cover_google_books(title=book_name, author=author, file_path=file_path)
                    return filename, size
            else:
                logger.error(f'Error descargando libro: no ha sido posible encontrar el link de descarga')
                return None
        except requests.exceptions.Timeout:
            logger.error(f'Timeout error durante la descarga. URL: {download_url}')
            return None
        except Exception as e:
            logger.error(f'Error descargando libro: {str(e)}')
            return None



    def batch_download_books(self, urls_from_author:list, author:str):
        ''' Download all book collection from a given author'''
        for url in urls_from_author:
            self.download_book(url, author)
            time.sleep(2)


    def get_book_page_list(self, page:int) -> list:
        ''' Get list of book titles for a given page number '''
        page_url = f'https://ww3.lectulandia.com/book/page/{page}/'
        self.browser.open(page_url)
        logger.info(f'Obteniendo lista de libros desde {page_url}')
        book_page_list = [
            f"https://ww3.lectulandia.com{book['href']}"
            for book in self.browser.find_all("a", class_="card-click-target")]
        return book_page_list


    def download_full_page(self, page:int):
        ''' Download a full page '''
        logger.info(f"Descargando página: {page} ")
        try:
            books = self.get_book_page_list(page)
            for book in books:
                time.sleep(1)
                download_url = self.get_download_link(book)
        except Exception as e:
            logger.error(f'Error descargando página completa: {str(e)}')