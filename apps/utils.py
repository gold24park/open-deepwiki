import asyncio
import glob
import os
import shutil
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Awaitable, Callable, ParamSpec, TypeVar

import tiktoken

from apps.settings import CONFIG, Logger


def count_tokens(text: str) -> int:
    try:
        encoding = tiktoken.encoding_for_model(CONFIG["tokenizer"]["model"])
        return len(encoding.encode(text))
    except Exception as e:
        Logger.warning(f"Token count error: {e}", exc_info=True)
        # If there's an error in tiktoken,
        # calculate an approximate token count as an alternative method
        return len(text) // 4


def sha1_hash(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def filter_files(
    path: str, exts: list[str], excluded_dirs: list, excluded_files: list
):
    files = glob.glob(f"{path}/**/*", recursive=True)
    for file_path in files:
        _ext = os.path.splitext(file_path)[1]
        is_excluded = False
        if os.path.isdir(file_path):
            is_excluded = True
        if not is_excluded and _ext != "" and _ext not in exts:
            is_excluded = True
        if any(excluded_dir in file_path for excluded_dir in excluded_dirs):
            is_excluded = True
        if not is_excluded and any(
            os.path.basename(file_path) == excluded
            for excluded in excluded_files
        ):
            is_excluded = True
        if is_excluded:
            continue
        yield file_path


def move_files(src_dir: str, dst_dir: str):
    """Moves all files under src_dir to dst_dir."""
    for root, _, files in os.walk(src_dir):
        for file in files:
            src_file = Path(root) / file
            dst_file = Path(dst_dir) / os.path.relpath(src_file, src_dir)
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            shutil.move(src_file, dst_file)


def normalize_path(path: str) -> str:
    """Normalizes the path."""
    if path and (path[0] == "/" or path[0] == "."):
        path = path[1:]
    return path


def parse_duration(duration_str: str) -> timedelta:
    """
    Converts a duration string to a timedelta object.

    Supported formats:
    - 1w (1 week)
    - 2d (2 days)
    - 3h (3 hours)
    - 4m (4 minutes)
    - 5s (5 seconds)
    - 1w2d3h4m5s (1 week 2 days 3 hours 4 minutes 5 seconds)

    """
    duration_str = duration_str.lower()
    total_seconds = Decimal("0")
    prev_num = []
    for character in duration_str:
        if character.isalpha():
            if prev_num:
                num = Decimal("".join(prev_num))
                match character:
                    case "w":
                        total_seconds += num * 60 * 60 * 24 * 7
                    case "d":
                        total_seconds += num * 60 * 60 * 24
                    case "h":
                        total_seconds += num * 60 * 60
                    case "m":
                        total_seconds += num * 60
                    case "s":
                        total_seconds += num
                prev_num = []
        elif character.isnumeric() or character == ".":
            prev_num.append(character)
    return timedelta(seconds=float(total_seconds))


P = ParamSpec("P")
T = TypeVar("T")


def make_sync(async_func: Callable[P, Awaitable[T]]) -> Callable[P, T]:
    """
    Converts an asynchronous function to a synchronous function.

    Args:
        async_func (Callable[P, Awaitable[T]]): Asynchronous function

    Returns:
        Callable[P, T]: Synchronous function
    """

    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError as e:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(async_func(*args, **kwargs))

    return sync_wrapper
