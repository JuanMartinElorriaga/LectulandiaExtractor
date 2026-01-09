"""Validation and sanitization utilities."""
import re
import zipfile
from pathlib import Path
from loguru import logger


def validate_epub(file_path: Path) -> bool:
    """
    Validate that a file is a valid EPUB (ZIP with mimetype).

    Args:
        file_path: Path to the EPUB file

    Returns:
        True if valid EPUB, False otherwise
    """
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            # EPUB must have 'mimetype' file
            if 'mimetype' not in zf.namelist():
                logger.error(f"EPUB inválido: falta archivo 'mimetype' en {file_path.name}")
                return False

            # Verify mimetype content
            mimetype = zf.read('mimetype').decode('utf-8').strip()
            if mimetype != 'application/epub+zip':
                logger.error(f"EPUB inválido: mimetype incorrecto '{mimetype}' en {file_path.name}")
                return False

            return True

    except zipfile.BadZipFile:
        logger.error(f"EPUB corrupto: no es un archivo ZIP válido - {file_path.name}")
        return False
    except Exception as e:
        logger.error(f"Error validando EPUB {file_path.name}: {e}")
        return False


def sanitize_filename(name: str) -> str:
    """
    Remove dangerous characters and prevent path traversal.

    Removes:
    - Invalid filename characters: < > : " / \\ | ? *
    - Path traversal patterns: ..
    - Multiple spaces

    Args:
        name: Original filename/dirname

    Returns:
        Sanitized safe filename

    Examples:
        >>> sanitize_filename("../../malicious")
        'malicious'
        >>> sanitize_filename("file<>name:test")
        'filenametest'
    """
    # Remove invalid characters
    safe_name = re.sub(r'[<>:"/\\|?*]', '', name)

    # Prevent path traversal
    safe_name = safe_name.replace('..', '')

    # Normalize multiple spaces to single space
    safe_name = re.sub(r'\s+', ' ', safe_name)

    # Remove leading/trailing whitespace
    return safe_name.strip()


def sanitize_path(base_path: Path, *components: str) -> Path:
    """
    Construct a safe path, validating it doesn't escape base_path.

    Args:
        base_path: Base directory (must exist or be creatable)
        *components: Path components to join

    Returns:
        Resolved safe path

    Raises:
        ValueError: If path traversal detected

    Examples:
        >>> base = Path('/safe/base')
        >>> sanitize_path(base, 'author', 'book title')
        Path('/safe/base/author/book title')

        >>> sanitize_path(base, '..', '..', 'etc', 'passwd')
        ValueError: Path traversal detected
    """
    # Sanitize each component
    sanitized = [sanitize_filename(c) for c in components]

    # Build and resolve path
    full_path = base_path.joinpath(*sanitized).resolve()
    base_resolved = base_path.resolve()

    # Verify path is within base_path
    try:
        full_path.relative_to(base_resolved)
    except ValueError:
        raise ValueError(
            f"Path traversal detected: {full_path} escapes {base_resolved}"
        )

    return full_path
