import click
from urllib.parse import urlparse, unquote
from extractor import Downloader
import os

from calibre_utils import add_folder_to_calibre

@click.command()
@click.option('--author', prompt='Nombre de autor', help='Nombre de autor desde el cual descargar libros')
@click.option('--download_folder', prompt='Path de descarga', default=r'C:\Users\juanm\Documents\LIBROS', help='Directorio local en donde descargar los libros')
@click.option('--calibre_library', prompt='Path de base Calibre', default=r"D:\CalibreLib\Calibre Library", help='Directorio de la libreria Calibre')
@click.option('--proxy', default=None, help='Proxy para los requests')
def main(author, proxy, download_folder, calibre_library):
    downloader = Downloader(proxy, download_folder, calibre_library)

    try:
        author_url = downloader.get_author_url(author)
        click.echo(f'URL del autor: {author_url}')

        urls_from_author = downloader.get_urls_from_author_url(author_url)
        click.echo(f'Total de links encontrados para {author.title()}: {len(urls_from_author)}')

        # Display the list of URLs to the user
        click.echo(click.style('\nLista de libros:', fg='cyan'))

        for i, url in enumerate(urls_from_author, start=1):
            book = unquote(urlparse(url).path.strip('/').split('/')[-1]).replace('-', ' ')
            click.echo(f"{click.style(i, fg='yellow')}. {click.style(book, fg='yellow')}")


        # Prompt the user to select URLs for download
        selected_indices = click.prompt(
            'Seleccionar libro(s) para descargar (ej., 1,2,3, o ALL para todos)',
            type         = str,
            default      = 'ALL',
            show_default = True
        )

        # Filter the URLs based on user selection
        if selected_indices.upper() == 'ALL':
            selected_urls = urls_from_author
        else:
            selected_indices = selected_indices.split(',')
            selected_urls    = [urls_from_author[int(index) - 1] for index in selected_indices]

        #click.echo(f'Libros seleccionados: {selected_urls}')
        download_links = downloader.get_batch_download_links(selected_urls)
        click.echo(f'Total de libros a descargar de {author.title()}: {len(download_links)}')

        if not click.confirm('Quieres comenzar con la descarga?', default=True):
            raise click.Abort("❌ Descarga abortada por el usuario.")

        downloader.batch_download_books(download_links, author)
        click.echo(click.style('✔ Descarga finalizada!', fg='green'))

        # Agregar a Calibre (calibre.exe debe estar apagado)
        if click.confirm('Quieres actualizar la base de datos Calibre?', default=True):
            author_folder = os.path.join(download_folder, author)
            add_folder_to_calibre(author_folder, calibre_library)

    except Exception as e:
        click.echo(click.style(f'Error: {str(e)}', fg='red'))


if __name__ == '__main__':
    main()
