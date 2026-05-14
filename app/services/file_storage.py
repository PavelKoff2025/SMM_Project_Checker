import os
import re
import uuid
import zipfile
from typing import BinaryIO

ALLOWED_EXTENSIONS = {'.pdf', '.pptx'}
MAX_FILE_SIZE = 32 * 1024 * 1024

_PDF_MAGIC = b'%PDF'
_ZIP_MAGIC = b'PK\x03\x04'


class FileValidationError(ValueError):
    """Raised when the uploaded file fails validation."""


def sanitize_original_filename(filename: str) -> str:
    return re.sub(r'[<>&"\']', '', filename or '').strip()


def split_extension(filename: str) -> tuple[str, str]:
    _, ext = os.path.splitext(filename)
    return filename, ext.lower()


def _peek_stream(stream: BinaryIO, n: int) -> bytes:
    head = stream.read(n)
    stream.seek(0)
    return head


def _stream_size(stream: BinaryIO) -> int:
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    return size


def validate_upload(stream: BinaryIO, ext: str) -> None:
    """Validate extension, size, and magic bytes from a file-like object.

    Must be called before persisting the stream to disk so that invalid files
    never touch the filesystem.
    """
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f'Недопустимый формат. Разрешены: {", ".join(sorted(ALLOWED_EXTENSIONS))}'
        )

    size = _stream_size(stream)
    if size == 0:
        raise FileValidationError('Файл пустой.')
    if size > MAX_FILE_SIZE:
        raise FileValidationError('Файл превышает лимит 32 МБ.')

    head = _peek_stream(stream, 8)
    if ext == '.pdf' and not head.startswith(_PDF_MAGIC):
        raise FileValidationError('Файл не является валидным PDF.')
    if ext == '.pptx' and not head.startswith(_ZIP_MAGIC):
        raise FileValidationError('Файл не является валидным PPTX.')


def persist_upload(stream: BinaryIO, upload_dir: str, ext: str) -> tuple[str, str]:
    """Save a pre-validated stream and return (safe_filename, absolute_path).

    For PPTX, additionally verifies the archive structure after writing.
    """
    os.makedirs(upload_dir, exist_ok=True)
    safe_filename = f'{uuid.uuid4()}{ext}'
    file_path = os.path.join(upload_dir, safe_filename)

    stream.seek(0)
    with open(file_path, 'wb') as fh:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)

    if ext == '.pptx':
        try:
            with zipfile.ZipFile(file_path) as zf:
                names = zf.namelist()
            if 'ppt/presentation.xml' not in names:
                os.remove(file_path)
                raise FileValidationError('Файл не является валидным PPTX.')
        except zipfile.BadZipFile as exc:
            os.remove(file_path)
            raise FileValidationError('Файл не является валидным PPTX.') from exc

    return safe_filename, file_path


def delete_silently(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
