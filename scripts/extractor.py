from loguru import logger
import os
import re
from rapidfuzz import fuzz
import sys
import time
from pathlib import Path
from unidecode import unidecode

# New imports - httpx + BeautifulSoup
import httpx
from src.infrastructure.http.http_client import HTTPClient
from src.utils.validators import validate_epub, sanitize_path
from src.utils.delays import smart_delay
from config.settings import settings

# Set logger to log into an external file as well as stream in the console
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
)
logger.add(
    "logs/downloader_{time:YYYY-MM-DD}.log",
    level="DEBUG",
    format="{time} - {level} - {name}:{function}:{line} - {message}",
    rotation="00:00",  # New file at midnight
    retention="30 days",
    compression="zip"
)


def clean_folder_name(name):
    """ Funcion helper para remover sufijo a las subcarpetas indexadas por Calibre """
    return re.sub(r'\s\(\d+\)$', '', name.strip())


class Downloader():
    def __init__(self, proxy: str, download_folder: str, calibre_library: str):
        self.download_folder = download_folder
        self.calibre_library = calibre_library
        self.http_client = HTTPClient(proxy=proxy)

    def _get_existing_author_folder(self, author_name_cleaned: str) -> tuple[str, list[str]]:
        """Busca coincidencia fuzzy en Calibre; si hay match, devuelve también subcarpetas"""
        threshold = settings.AUTHOR_MATCH_THRESHOLD
        best_match_name = None
        best_score = 0
        subfolders = []

        # Skip Calibre lookup if library path is empty or doesn't exist
        if not self.calibre_library or not os.path.isdir(self.calibre_library):
            logger.warning(f'Calibre library no configurada o no existe: "{self.calibre_library}"')
            normalized_capitalized = ' '.join(word.capitalize() for word in author_name_cleaned.split())
            final_path = os.path.join(self.download_folder, normalized_capitalized)
            if not os.path.exists(final_path):
                os.makedirs(final_path)
                logger.info(f'Carpeta creada: {final_path}')
            return final_path, []

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

    def _get_genre_folder(self, genre_name: str) -> tuple[str, list[str]]:
        """
        Create and return the genre folder path.

        Args:
            genre_name: Display name of the genre (e.g., "Arquitectura")

        Returns:
            tuple: (folder_path, existing_books_list)
        """
        # Capitalize genre name for folder
        folder_name = ' '.join(word.capitalize() for word in genre_name.split())
        final_path = os.path.join(self.download_folder, folder_name)

        existing_books = []

        # Create folder if it doesn't exist
        if not os.path.exists(final_path):
            os.makedirs(final_path)
            logger.info(f'Carpeta de género creada: {final_path}')
        else:
            logger.info(f'Carpeta de género ya existente: {final_path}')
            # Get existing book folders for duplicate detection
            existing_books = [f for f in os.listdir(final_path) if os.path.isdir(os.path.join(final_path, f))]

        return final_path, existing_books

    def get_author_url(self, author: str) -> str:
        ''' Get author url from author name '''
        # Input validation
        if not author or not isinstance(author, str):
            raise ValueError("El autor debe ser un string no nulo")

        # Check if base url is active
        base_url = settings.LECTULANDIA_BASE_URL
        try:
            response = httpx.head(base_url, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise httpx.ConnectError(f"La URL: {base_url} no se encuentra activa. Error: {e}")

        # Create author url
        author_name = author.replace(" ", "-").lower()
        author_url = f'{base_url}/autor/{author_name}'
        return author_url

    def get_urls_from_author_url(self, author_url: str, urls_from_author: list = None, depth: int = 0) -> list:
        """Get list of book links for a given author with pagination support."""
        if not urls_from_author:
            urls_from_author = []

        # Prevent infinite recursion
        if depth >= settings.MAX_PAGINATION_DEPTH:
            logger.warning(f"Alcanzado límite de paginación: {settings.MAX_PAGINATION_DEPTH} páginas")
            return urls_from_author

        # Use httpx + BeautifulSoup instead of RoboBrowser
        soup = self.http_client.get_soup(author_url)

        new_urls = [
            f"{settings.LECTULANDIA_BASE_URL}{book['href']}"
            for book in soup.find_all("a", class_="card-click-target")
        ]
        urls_from_author.extend(new_urls)

        # Check for next page
        next_page_link = soup.find("a", class_="next page-numbers")
        if next_page_link:
            smart_delay(1.0, 3.0)  # Smart delay between pages
            next_page_url = f"{settings.LECTULANDIA_BASE_URL}{next_page_link['href']}"
            # Recursive call with depth tracking
            self.get_urls_from_author_url(next_page_url, urls_from_author, depth + 1)

        if not urls_from_author:
            raise Exception("No hay URLs para este autor! Intentar un autor distinto.")

        return urls_from_author

    def get_available_genres(self) -> dict[str, str]:
        """
        Fetch available genres from the website.
        
        Returns:
            dict: {display_name: slug} (e.g., {"Arquitectura": "arquitectura"})
        """
        # Genres are listed on the main page
        genres_url = settings.LECTULANDIA_BASE_URL
        logger.info(f"Obteniendo géneros desde: {genres_url}")

        soup = self.http_client.get_soup(genres_url)
        genres = {}

        # Find all genre links in the page
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if "/genero/" in href:
                # Extract slug from URL like "/genero/arquitectura/"
                slug = href.strip("/").split("/")[-1]
                display_name = link.get_text(strip=True)
                if display_name and slug:
                    genres[display_name] = slug

        if not genres:
            raise Exception("No se pudieron obtener los géneros desde el sitio.")

        logger.info(f"Se encontraron {len(genres)} géneros")
        return genres

    def get_genre_url(self, genre_slug: str) -> str:
        """
        Get genre URL from genre slug.

        Args:
            genre_slug: The genre slug (e.g., "arquitectura")

        Returns:
            Full genre URL
        """
        if not genre_slug or not isinstance(genre_slug, str):
            raise ValueError("El género debe ser un string no nulo")

        base_url = settings.LECTULANDIA_BASE_URL
        genre_url = f'{base_url}/genero/{genre_slug}'
        return genre_url

    def get_urls_from_genre_url(self, genre_url: str, urls_from_genre: list = None, depth: int = 0) -> list:
        """
        Get list of book links for a given genre with pagination support.

        Args:
            genre_url: URL of the genre page
            urls_from_genre: Accumulated URLs (for recursion)
            depth: Current pagination depth

        Returns:
            List of book URLs
        """
        if not urls_from_genre:
            urls_from_genre = []

        # Prevent infinite recursion
        if depth >= settings.MAX_PAGINATION_DEPTH:
            logger.warning(f"Alcanzado límite de paginación: {settings.MAX_PAGINATION_DEPTH} páginas")
            return urls_from_genre

        soup = self.http_client.get_soup(genre_url)

        new_urls = [
            f"{settings.LECTULANDIA_BASE_URL}{book['href']}"
            for book in soup.find_all("a", class_="card-click-target")
        ]
        urls_from_genre.extend(new_urls)

        # Check for next page
        next_page_link = soup.find("a", class_="next page-numbers")
        if next_page_link:
            smart_delay(1.0, 3.0)  # Smart delay between pages
            next_page_url = f"{settings.LECTULANDIA_BASE_URL}{next_page_link['href']}"
            # Recursive call with depth tracking
            self.get_urls_from_genre_url(next_page_url, urls_from_genre, depth + 1)

        if not urls_from_genre:
            raise Exception("No hay URLs para este género! Intentar un género distinto.")

        return urls_from_genre

    def get_download_link(self, book_url: str):
        """Turn book link into a download url."""
        soup = self.http_client.get_soup(book_url)

        for link in soup.find_all("a"):
            if "download.php?t=1" in str(link):
                # Note: download.php is on www, not ww3
                return f"https://www.lectulandia.com{link['href']}"

        return None

    def get_batch_download_links(self, urls_from_author: list) -> tuple[list, list]:
        """
        Get whole list of links to download from a given author.

        Returns:
            tuple: (download_links, failed_urls) - successful links and URLs that failed
        """
        download_links = []
        failed_urls = []
        for book_url in urls_from_author:
            try:
                link = self.get_download_link(book_url)
                if link:
                    download_links.append(link)
            except Exception as e:
                logger.error(f"Error obteniendo link de descarga para {book_url}: {e}")
                failed_urls.append({'url': book_url, 'error': str(e)})
                continue
        return download_links, failed_urls

    def download_book(self, download_url: str, author: str = None, timeout: int = None, folder_name: str = None, direct_mode: bool = False) -> None:
        """
        Download a single book with validation.

        Args:
            download_url: URL to download from
            author: Author name (used for folder organization in author mode)
            timeout: Download timeout in seconds
            folder_name: Optional folder name override (used for genre mode)
            direct_mode: If True, creates Author/Book structure directly in download_folder
        """
        if timeout is None:
            timeout = settings.DOWNLOAD_TIMEOUT

        try:
            logger.info(f'Descargando desde: {download_url}')

            # Get linkCode from download page
            soup = self.http_client.get_soup(download_url)
            pattern = re.compile(r'var linkCode = "(.*?)";')
            match = pattern.search(str(soup))

            if not match:
                raise ValueError("No se pudo extraer linkCode de download.php")

            link_code = match.group(1)
            ant_url = f'{settings.ANTUPLOAD_BASE_URL}/file/{link_code}'
            logger.info(f'antupload: {ant_url}')

            # Get file info from antupload
            ant_soup = self.http_client.get_soup(ant_url)
            file_desc = ant_soup.find("div", id="fileDescription")

            if not file_desc:
                raise ValueError("No se encontró información del archivo en antupload")

            paragraphs = file_desc.find_all("p")
            raw_filename = paragraphs[1].text.replace("Name: ", "")
            size = paragraphs[2].text

            # Extract book name and author from filename (format: "BookName - Author.epub")
            name_without_ext = os.path.splitext(raw_filename)[0]
            parts = name_without_ext.split(" - ")
            book_name = parts[0].strip()
            # Extract author from filename if available
            file_author = parts[1].strip() if len(parts) > 1 else "Autor Desconocido"
            filename = f"{book_name}.epub"

            # Determine target folder based on mode
            if direct_mode:
                # Direct mode (catalog): downloads/Author/Book/ - use extracted author
                author_name_cleaned = unidecode(file_author).strip().lower()
                target_folder, existing_books = self._get_existing_author_folder(author_name_cleaned)
            elif folder_name:
                # Genre mode: Genre/Author/Book/
                target_folder, existing_books = self._get_genre_folder(folder_name)
            elif author:
                # Author mode: Author/Book/ with Calibre lookup
                author_name_cleaned = unidecode(author).strip().lower()
                target_folder, existing_books = self._get_existing_author_folder(author_name_cleaned)
            else:
                raise ValueError("Debe especificar author, folder_name, o direct_mode=True")

            # Fuzzy match verification against existing books
            threshold = settings.BOOK_MATCH_THRESHOLD
            book_name_cleaned = unidecode(book_name).strip().lower()
            for existing in existing_books:
                existing_cleaned = unidecode(existing).strip().lower()
                score = fuzz.ratio(existing_cleaned, book_name_cleaned)
                if score >= threshold:
                    logger.info(f'Se detectó un libro similar ya existente: "{existing}" (score: {score}%). Se omite la descarga.')
                    return None

            # Build folder path based on mode
            if folder_name:
                # Genre mode: Genre/Author/BookName/
                book_folder = sanitize_path(Path(target_folder), file_author, book_name)
            else:
                # Author mode or Direct mode: Author/BookName/
                book_folder = sanitize_path(Path(target_folder), book_name)

            if book_folder.exists():
                logger.info(f'El libro ya existe en la carpeta destino: {book_folder}. Se omite la descarga.')
                return None
            else:
                book_folder.mkdir(parents=True, exist_ok=True)

            file_path = book_folder / filename

            # Find download button
            download_button = ant_soup.find("a", id="downloadB")
            if not download_button or not download_button.get('href'):
                raise ValueError("No se encontró botón de descarga en antupload")

            file_url = download_button['href']

            # Ensure URL is absolute
            if file_url.startswith('/'):
                file_url = f"{settings.ANTUPLOAD_BASE_URL}{file_url}"

            logger.info(f"Nombre de archivo: {filename}")
            logger.info(f"Tamaño de archivo: {size}")
            logger.info(f"URL de descarga: {file_url}")

            # Download binary content
            smart_delay(1.0, 2.0)  # Small delay before download
            binary_content = self.http_client.download_binary(
                file_url,
                timeout=timeout,
                referer=ant_url  # Add Referer header for anti-bot protection
            )

            # Save EPUB file
            with open(file_path, "wb") as epub_file:
                epub_file.write(binary_content)
                logger.info(f'El archivo ha sido descargado en: {epub_file.name}')

            # Validate EPUB
            if not validate_epub(file_path):
                logger.error(f"EPUB inválido o corrupto: {file_path}")
                os.remove(file_path)
                raise ValueError(f"El archivo descargado no es un EPUB válido")

            return filename, size

        except httpx.TimeoutException:
            logger.error(f'Timeout error durante la descarga. URL: {download_url}')
            return None
        except Exception as e:
            logger.error(f'Error descargando libro: {str(e)}')
            return None

    def batch_download_books(self, download_urls: list, author: str = None, folder_name: str = None, direct_mode: bool = False) -> dict:
        """
        Download all books from a list with result tracking.

        Args:
            download_urls: List of download URLs
            author: Author name (for author mode)
            folder_name: Folder name override (for genre mode)
            direct_mode: If True, creates Author/Book structure directly in download_folder

        Returns:
            dict with keys: 'exitosos', 'fallidos', 'omitidos'
        """
        results = {
            'exitosos': [],
            'fallidos': [],
            'omitidos': []
        }

        total = len(download_urls)
        display_name = folder_name if folder_name else (author.title() if author else "Catálogo")

        for i, url in enumerate(download_urls, 1):
            logger.info(f"Procesando libro {i}/{total}")

            try:
                result = self.download_book(url, author=author, folder_name=folder_name, direct_mode=direct_mode)

                if result is None:
                    results['omitidos'].append(url)
                    logger.info(f"Libro omitido (ya existe o duplicado)")
                else:
                    results['exitosos'].append({'url': url, 'filename': result[0], 'size': result[1]})
                    logger.info(f"✓ Descargado: {result[0]}")

            except Exception as e:
                results['fallidos'].append({'url': url, 'error': str(e)})
                logger.error(f"✗ Error en {url}: {str(e)}")
                # Continue with next book without interrupting batch

            # Smart delay between downloads
            if i < total:  # Don't delay after last book
                smart_delay()  # Uses configured defaults

        # Final summary
        logger.info(f"\n{'='*50}")
        logger.info(f"RESUMEN DE DESCARGA - {display_name}")
        logger.info(f"Exitosos: {len(results['exitosos'])}")
        logger.info(f"Omitidos: {len(results['omitidos'])} (ya existían)")
        logger.info(f"Fallidos: {len(results['fallidos'])}")
        logger.info(f"{'='*50}\n")

        return results

    def __del__(self):
        """Cleanup: close HTTP client when Downloader is destroyed."""
        if hasattr(self, 'http_client'):
            self.http_client.close()
