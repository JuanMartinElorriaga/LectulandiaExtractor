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


def download_with_progress(downloader: Downloader, download_links: list, author: str = None, folder_name: str = None) -> dict:
    """Download books with a nice progress display."""
    display_name = folder_name if folder_name else author.title()

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
                result = downloader.download_book(url, author=author, folder_name=folder_name)

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


def search_by_genre(downloader: Downloader, dry_run: bool, download_folder: str):
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

        # Search mode selection
        search_mode = inquirer.select(
            message="¿Cómo quieres buscar?",
            choices=[
                {"name": "📝 Por Autor", "value": "autor"},
                {"name": "📚 Por Género", "value": "genero"},
                Separator(),
                {"name": "❌ Salir", "value": "exit"},
            ],
            default="autor",
        ).execute()

        if search_mode == "exit":
            console.print("[dim]¡Hasta luego! 👋[/dim]")
            return

        # Initialize downloader
        downloader = Downloader(proxy=None, download_folder=download_folder, calibre_library=calibre_library)

        if search_mode == "autor":
            search_by_author(downloader, dry_run, download_folder, calibre_library)
        else:
            search_by_genre(downloader, dry_run, download_folder)

    except KeyboardInterrupt:
        console.print("\n[yellow]Operación cancelada por el usuario.[/yellow]")
    except Exception as e:
        console.print(f"\n[red bold]Error:[/red bold] {str(e)}")


if __name__ == '__main__':
    main()
