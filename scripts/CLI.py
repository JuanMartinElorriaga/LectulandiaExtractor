import os
from urllib.parse import urlparse, unquote

from InquirerPy import inquirer
from InquirerPy.separator import Separator
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn, TaskProgressColumn
from rich.text import Text
from rich import box

from extractor import Downloader
from calibre_utils import add_folder_to_calibre
from config.settings import settings
from searcher import BookSearcher, display_search_results
from indexer import rebuild_index, update_index, get_index_info
import database as db

console = Console()


def show_banner():
    """Display welcome banner."""
    banner = Text()
    banner.append("📚 ", style="bold")
    banner.append("Lectulandia Extractor", style="bold cyan")
    banner.append("\n")
    banner.append("Descarga libros en español fácilmente", style="dim")

    console.print(Panel(
        banner,
        border_style="cyan",
        padding=(1, 2),
    ))
    console.print()


def show_config_panel(download_folder: str, calibre_library: str):
    """Display current configuration."""
    table = Table(box=box.ROUNDED, show_header=False, border_style="dim")
    table.add_column("Key", style="dim")
    table.add_column("Value", style="cyan")

    table.add_row("📁 Carpeta descarga", download_folder)
    table.add_row("📖 Librería Calibre", calibre_library or "[dim]No configurada[/dim]")

    console.print(Panel(table, title="[bold]Configuración[/bold]", border_style="blue", padding=(0, 1)))
    console.print()


def extract_book_name(url: str) -> str:
    """Extract readable book name from URL."""
    return unquote(urlparse(url).path.strip('/').split('/')[-1]).replace('-', ' ').title()


def select_books_interactive(book_urls: list, title: str) -> list:
    """Interactive book selection with checkboxes."""
    choices = [
        {"name": f"{extract_book_name(url)}", "value": url}
        for url in book_urls
    ]

    console.print(f"\n[cyan]📚 {len(book_urls)} libros encontrados en {title}[/cyan]\n")

    selected = inquirer.checkbox(
        message="Seleccionar libros para descargar",
        choices=choices,
        cycle=True,
        instruction="(↑↓ navegar, espacio marcar, ctrl+a todos, enter confirmar)",
        keybindings={
            "toggle-all-true": [{"key": "c-a"}],  # Ctrl+A para seleccionar todos
            "toggle-all-false": [{"key": "c-a"}],  # Ctrl+A también deselecciona todos
        },
    ).execute()

    return selected if selected else []


def show_books_table(book_urls: list, title: str):
    """Display books in a styled table."""
    table = Table(
        title=f"[bold cyan]📚 Libros en {title}[/bold cyan]",
        box=box.ROUNDED,
        show_lines=False,
        header_style="bold magenta",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Título", style="white")

    for i, url in enumerate(book_urls, start=1):
        book_name = extract_book_name(url)
        table.add_row(str(i), book_name)

    console.print(table)
    console.print()


def download_with_progress(downloader: Downloader, download_links: list, author: str = None, folder_name: str = None, direct_mode: bool = False) -> dict:
    """Download books with a nice progress display."""
    if direct_mode:
        display_name = "Catálogo"
    elif folder_name:
        display_name = folder_name
    elif author:
        display_name = author.title()
    else:
        display_name = "Descarga"

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task(
            f"Descargando de {display_name}",
            total=len(download_links)
        )

        results = {
            'exitosos': [],
            'fallidos': [],
            'omitidos': []
        }

        for url in download_links:
            try:
                result = downloader.download_book(url, author=author, folder_name=folder_name, direct_mode=direct_mode)

                if result is None:
                    results['omitidos'].append(url)
                else:
                    results['exitosos'].append({'url': url, 'filename': result[0], 'size': result[1]})
            except Exception as e:
                results['fallidos'].append({'url': url, 'error': str(e)})

            progress.update(task, advance=1)

    return results


def show_results(title: str, failed_links: list, results: dict):
    """Display download results in a styled panel."""
    all_failures = failed_links + results['fallidos']

    # Summary table
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
    table.add_column("Estado", style="bold")
    table.add_column("Cantidad", justify="center")

    table.add_row("✅ Exitosos", f"[green bold]{len(results['exitosos'])}[/green bold]")
    table.add_row("⏭️  Omitidos", f"[yellow]{len(results['omitidos'])}[/yellow]")
    table.add_row("❌ Fallidos", f"[red]{len(all_failures)}[/red]")

    console.print(Panel(
        table,
        title=f"[bold]Resumen - {title}[/bold]",
        border_style="green" if not all_failures else "yellow",
        padding=(1, 2),
    ))

    # Show failed books if any
    if all_failures:
        console.print("\n[red bold]Libros fallidos:[/red bold]")
        for item in all_failures:
            console.print(f"  [red]•[/red] {item.get('url', 'URL desconocida')}")
            if 'error' in item:
                console.print(f"    [dim]{item['error']}[/dim]")

    console.print("\n[green bold]✨ Proceso finalizado![/green bold]\n")


def search_by_author(downloader: Downloader, dry_run: bool, download_folder: str, calibre_library: str):
    """Handle author search mode."""
    author = inquirer.text(
        message="Nombre del autor",
        validate=lambda x: len(x) > 0,
        invalid_message="El nombre no puede estar vacío",
    ).execute()

    with console.status(f"[cyan]Buscando libros de {author.title()}...[/cyan]", spinner="dots"):
        author_url = downloader.get_author_url(author)
        book_urls = downloader.get_urls_from_author_url(author_url)

    console.print(f"[green]✓[/green] URL del autor: [dim]{author_url}[/dim]")

    # Interactive book selection
    selected_urls = select_books_interactive(book_urls, author.title())
    if not selected_urls:
        # If nothing selected, ask if they want all
        select_all = inquirer.confirm(
            message="No seleccionaste ningún libro. ¿Descargar todos?",
            default=False,
        ).execute()
        if select_all:
            selected_urls = book_urls
        else:
            console.print("[yellow]Operación cancelada.[/yellow]")
            return

    # Get download links
    with console.status("[cyan]Obteniendo links de descarga...[/cyan]", spinner="dots"):
        download_links, failed_links = downloader.get_batch_download_links(selected_urls)

    console.print(f"\n[cyan]📥 {len(download_links)} libros listos para descargar[/cyan]")
    if failed_links:
        console.print(f"[yellow]⚠️  {len(failed_links)} no pudieron obtener link[/yellow]")

    # Dry-run mode
    if dry_run:
        console.print(Panel(
            "\n".join([f"• {extract_book_name(link)}" for link in download_links[:10]]) +
            (f"\n... y {len(download_links) - 10} más" if len(download_links) > 10 else ""),
            title="[yellow]MODO DRY-RUN - Vista previa[/yellow]",
            border_style="yellow"
        ))
        return

    if not download_links:
        console.print("[yellow]No hay libros para descargar.[/yellow]")
        return

    # Confirm download
    confirm = inquirer.confirm(
        message=f"¿Comenzar descarga de {len(download_links)} libros?",
        default=True,
    ).execute()

    if not confirm:
        console.print("[yellow]Descarga cancelada.[/yellow]")
        return

    # Download
    results = download_with_progress(downloader, download_links, author=author)
    show_results(author.title(), failed_links, results)

    # Calibre integration
    if calibre_library:
        add_to_calibre = inquirer.confirm(
            message="¿Actualizar base de datos Calibre?",
            default=True,
        ).execute()

        if add_to_calibre:
            author_folder = os.path.join(download_folder, author)
            add_folder_to_calibre(author_folder, calibre_library)


def search_by_genre(downloader: Downloader, dry_run: bool, download_folder: str, calibre_library: str = None):
    """Handle genre search mode."""
    with console.status("[cyan]Obteniendo géneros disponibles...[/cyan]", spinner="dots"):
        genres = downloader.get_available_genres()

    genre_list = list(genres.items())

    # Interactive genre selection
    genre_choices = [{"name": name, "value": (name, slug)} for name, slug in genre_list]

    selected_genre_name, selected_genre_slug = inquirer.fuzzy(
        message="Seleccionar género (escribe para filtrar)",
        choices=genre_choices,
        max_height="70%",
    ).execute()

    console.print(f"\n[green]✓[/green] Género seleccionado: [cyan bold]{selected_genre_name}[/cyan bold]")

    # Get books from genre
    with console.status(f"[cyan]Buscando libros en {selected_genre_name}...[/cyan]", spinner="dots"):
        genre_url = downloader.get_genre_url(selected_genre_slug)
        book_urls = downloader.get_urls_from_genre_url(genre_url)

    console.print(f"[green]✓[/green] URL del género: [dim]{genre_url}[/dim]")

    # Interactive book selection
    selected_urls = select_books_interactive(book_urls, selected_genre_name)
    if not selected_urls:
        select_all = inquirer.confirm(
            message="No seleccionaste ningún libro. ¿Descargar todos?",
            default=False,
        ).execute()
        if select_all:
            selected_urls = book_urls
        else:
            console.print("[yellow]Operación cancelada.[/yellow]")
            return

    # Get download links
    with console.status("[cyan]Obteniendo links de descarga...[/cyan]", spinner="dots"):
        download_links, failed_links = downloader.get_batch_download_links(selected_urls)

    console.print(f"\n[cyan]📥 {len(download_links)} libros listos para descargar[/cyan]")
    if failed_links:
        console.print(f"[yellow]⚠️  {len(failed_links)} no pudieron obtener link[/yellow]")

    # Dry-run mode
    if dry_run:
        console.print(Panel(
            "\n".join([f"• {extract_book_name(link)}" for link in download_links[:10]]) +
            (f"\n... y {len(download_links) - 10} más" if len(download_links) > 10 else ""),
            title="[yellow]MODO DRY-RUN - Vista previa[/yellow]",
            border_style="yellow",
        ))
        return

    if not download_links:
        console.print("[yellow]No hay libros para descargar.[/yellow]")
        return

    # Confirm download
    confirm = inquirer.confirm(
        message=f"¿Comenzar descarga de {len(download_links)} libros?",
        default=True,
    ).execute()

    if not confirm:
        console.print("[yellow]Descarga cancelada.[/yellow]")
        return

    # Download
    results = download_with_progress(downloader, download_links, folder_name=selected_genre_name)
    show_results(selected_genre_name, failed_links, results)

    # Calibre sync - sync the genre folder (contains Author/Book structure)
    if calibre_library and results:
        genre_folder = os.path.join(download_folder, selected_genre_name)
        if os.path.exists(genre_folder):
            add_to_calibre = inquirer.confirm(
                message="¿Agregar a Calibre?",
                default=True,
            ).execute()

            if add_to_calibre:
                add_folder_to_calibre(genre_folder, calibre_library)


def search_in_catalog(downloader: Downloader, dry_run: bool, download_folder: str, calibre_library: str = None):
    """Search for books in the local catalog index."""
    searcher = BookSearcher()

    # Check if index exists
    if not searcher.is_available():
        console.print("\n[yellow]⚠️  El índice del catálogo no está disponible.[/yellow]")
        create_now = inquirer.confirm(
            message="¿Deseas crear el índice ahora? (puede tomar varios minutos)",
            default=True,
        ).execute()

        if create_now:
            do_rebuild_index()
            searcher = BookSearcher()  # Reload
        else:
            return

    # Show index info
    info = searcher.get_index_info()
    if info:
        last_updated = info.get('last_updated', 'Desconocido')
        if len(last_updated) > 19:
            last_updated = last_updated[:19].replace('T', ' ')
        console.print(Panel(
            f"📚 [cyan]{info.get('total_books', 0)}[/cyan] libros indexados\n"
            f"🕐 Actualizado: [dim]{last_updated}[/dim]",
            title="[bold]Índice del Catálogo[/bold]",
            border_style="blue",
        ))

    # Search loop
    while True:
        # Ask what to search by
        search_type = inquirer.select(
            message="¿Qué deseas buscar?",
            choices=[
                {"name": "📖 Buscar por título", "value": "title"},
                {"name": "✍️  Buscar por autor", "value": "author"},
                {"name": "🔍 Buscar en todo", "value": "all"},
                {"name": "← Volver", "value": "exit"},
            ],
            default="all",
        ).execute()

        if search_type == "exit":
            break

        search_label = {
            "title": "título",
            "author": "autor",
            "all": "título o autor"
        }[search_type]

        query = inquirer.text(
            message=f"Buscar {search_label}",
            validate=lambda x: len(x) > 0,
        ).execute()

        results = searcher.search(query, search_by=search_type, limit=15)
        display_search_results(results, query)

        if results:
            # Ask if user wants to download any
            download_choice = inquirer.confirm(
                message="¿Deseas descargar alguno de estos libros?",
                default=False,
            ).execute()

            if download_choice:
                # Let user select which books
                choices = [
                    {"name": f"{book['title']} - {book.get('author', '?')}", "value": book['url']}
                    for book in results
                ]

                selected_urls = inquirer.checkbox(
                    message="Seleccionar libros para descargar",
                    choices=choices,
                    cycle=True,
                    instruction="(↑↓ navegar, espacio marcar, ctrl+a todos, enter confirmar)",
                    keybindings={
                        "toggle-all-true": [{"key": "c-a"}],
                        "toggle-all-false": [{"key": "c-a"}],
                    },
                ).execute()

                if selected_urls:
                    # Get download links
                    with console.status("[cyan]Obteniendo links de descarga...[/cyan]", spinner="dots"):
                        download_links, failed_links = downloader.get_batch_download_links(selected_urls)

                    if download_links and not dry_run:
                        # Direct mode: Author/Book structure directly in download_folder
                        results_dl = download_with_progress(downloader, download_links, direct_mode=True)
                        show_results("Catálogo", failed_links, results_dl)

                        # Calibre sync - sync entire download folder
                        if calibre_library and results_dl.get('exitosos'):
                            add_to_calibre_choice = inquirer.confirm(
                                message="¿Agregar a Calibre?",
                                default=True,
                            ).execute()
                            if add_to_calibre_choice:
                                add_folder_to_calibre(download_folder, calibre_library)
                    elif dry_run:
                        console.print(Panel(
                            "\n".join([f"• {extract_book_name(link)}" for link in download_links]),
                            title="[yellow]MODO DRY-RUN[/yellow]",
                            border_style="yellow",
                        ))

                    break  # Exit search loop after download

        # Loop continues automatically to search type selection


def do_update_index():
    """Update the catalog index incrementally (only new books)."""
    max_pages = inquirer.number(
        message="Total de páginas a revisar",
        default=10,
        min_allowed=1,
        max_allowed=100,
    ).execute()

    try:
        update_index(max_pages=int(max_pages))
    except Exception as e:
        console.print(f"[red]Error al actualizar índice: {e}[/red]")


def do_rebuild_index():
    """Rebuild the catalog index from scratch."""
    console.print("\n[bold yellow]⚠️  Esto eliminará el índice actual y lo reconstruirá desde cero.[/bold yellow]\n")

    max_pages = inquirer.number(
        message="Páginas a indexar (0 = todas)",
        default=0,
        min_allowed=0,
        max_allowed=500,
    ).execute()

    max_pages = int(max_pages) if int(max_pages) > 0 else None

    if max_pages is None:
        confirm = inquirer.confirm(
            message="¿Indexar TODAS las páginas? Esto puede tomar mucho tiempo",
            default=False,
        ).execute()

        if not confirm:
            console.print("[dim]Operación cancelada.[/dim]")
            return

    try:
        rebuild_index(max_pages=max_pages)
    except Exception as e:
        console.print(f"[red]Error al construir índice: {e}[/red]")


def do_migrate_json():
    """Migrate existing JSON index to SQLite database."""
    from pathlib import Path

    json_file = Path(__file__).parent.parent / "data" / "catalog_index.json"

    if not json_file.exists():
        console.print("[yellow]⚠️  No se encontró el archivo JSON de índice.[/yellow]")
        console.print(f"[dim]Buscado en: {json_file}[/dim]")
        return

    # Check file size
    size_mb = json_file.stat().st_size / (1024 * 1024)
    console.print(f"\n[cyan]📄 Archivo JSON encontrado:[/cyan] {size_mb:.1f} MB")

    confirm = inquirer.confirm(
        message="¿Migrar datos de JSON a SQLite?",
        default=True,
    ).execute()

    if not confirm:
        console.print("[dim]Operación cancelada.[/dim]")
        return

    try:
        with console.status("[cyan]Migrando datos...[/cyan]", spinner="dots"):
            count = db.migrate_from_json()

        console.print(f"\n[green bold]✅ Migración completada![/green bold]")
        console.print(f"   📚 [cyan]{count}[/cyan] libros migrados")
        console.print(f"   💾 Base de datos: [dim]{db.DB_FILE}[/dim]")
        console.print(f"\n[dim]El archivo JSON original se ha conservado como respaldo.[/dim]\n")
    except Exception as e:
        console.print(f"[red]Error durante la migración: {e}[/red]")


def main():
    """Main CLI entry point."""
    console.clear()
    show_banner()

    try:
        # Configuration
        download_folder = inquirer.filepath(
            message="Carpeta de descarga",
            default=settings.DEFAULT_DOWNLOAD_FOLDER,
            only_directories=True,
        ).execute()

        calibre_library = inquirer.filepath(
            message="Librería Calibre (Enter para omitir)",
            default=settings.DEFAULT_CALIBRE_LIBRARY or "",
            only_directories=True,
        ).execute()

        show_config_panel(download_folder, calibre_library)

        # Dry-run option
        dry_run = inquirer.confirm(
            message="¿Modo dry-run? (solo vista previa, default N)",
            default=False,
        ).execute()

        # Check if index exists for display
        index_info = get_index_info()
        if index_info:
            index_status = f" ({index_info['total_books']} libros)"
        else:
            index_status = " (no disponible)"

        # Check if JSON exists for migration option
        from pathlib import Path
        json_file = Path(__file__).parent.parent / "data" / "catalog_index.json"
        has_json = json_file.exists()

        # Build menu choices
        menu_choices = [
            {"name": f"🔍 Buscar en Catálogo{index_status}", "value": "search"},
            {"name": "📚 Buscar por Género (listado web)", "value": "genero"},
            {"name": "📝 Buscar por Autor (búsqueda web exacta)", "value": "autor"},
            Separator(),
            {"name": "🔄 Actualizar Índice (solo nuevos)", "value": "update"},
            {"name": "🔁 Reconstruir Índice (desde cero)", "value": "rebuild"},
        ]

        # Add migration option if JSON file exists
        if has_json:
            menu_choices.append({"name": "📦 Migrar JSON a SQLite (legacy)", "value": "migrate"})

        menu_choices.extend([
            Separator(),
            {"name": "❌ Salir", "value": "exit"},
        ])

        # Search mode selection
        search_mode = inquirer.select(
            message="¿Qué deseas hacer?",
            choices=menu_choices,
            default="search",
        ).execute()

        if search_mode == "exit":
            console.print("[dim]¡Hasta luego! 👋[/dim]")
            return

        if search_mode == "update":
            do_update_index()
            return

        if search_mode == "rebuild":
            do_rebuild_index()
            return

        if search_mode == "migrate":
            do_migrate_json()
            return

        # Initialize downloader for other modes
        downloader = Downloader(proxy=None, download_folder=download_folder, calibre_library=calibre_library)

        if search_mode == "autor":
            search_by_author(downloader, dry_run, download_folder, calibre_library)
        elif search_mode == "genero":
            search_by_genre(downloader, dry_run, download_folder, calibre_library)
        elif search_mode == "search":
            search_in_catalog(downloader, dry_run, download_folder, calibre_library)

    except KeyboardInterrupt:
        console.print("\n[yellow]Operación cancelada por el usuario.[/yellow]")
    except Exception as e:
        console.print(f"\n[red bold]Error:[/red bold] {str(e)}")


if __name__ == '__main__':
    main()
