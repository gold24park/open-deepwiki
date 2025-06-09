from abc import abstractmethod
from enum import Enum, auto
from pathlib import Path

from langchain_text_splitters import TokenTextSplitter
from pydantic import BaseModel

from apps.settings import MAX_INPUT_TOKENS, Logger


class Observation(BaseModel):
    @abstractmethod
    def render(self) -> str:
        pass


class FileNotFoundError(Exception):
    """
    Exception raised when a file is not found.
    """

    pass


class TextSplitCriteria(Enum):
    LENGTH = auto()
    TOKEN_COUNT = auto()


def read_file_content(
    file_path: Path,
    ignore_errors: bool = False,
    split_criteria: TextSplitCriteria = TextSplitCriteria.LENGTH,
    split_size: int = -1,
) -> str:
    """
    Read a file and truncate its content if necessary.

    Args:
        file_path (Path): The path to the file to read.
        split_criteria (TextSplitCriteria): The criteria for splitting the content.
            - LENGTH: Split based on character count
            - TOKEN_COUNT: Split based on token count
        split_size (int): The size at which to truncate content. Default is -1 (no truncation).
        ignore_errors (bool): Whether to ignore errors during file reading.
            Default is False. If True, returns an empty string when an error occurs.

    Raises:
        FileNotFoundError: Raised when the file cannot be found
        FileReadError: Raised when there's an issue reading the file
    """
    try:
        if not file_path.exists():
            raise FileNotFoundError(f"File {file_path} not found.")

        truncated_message = "...[truncated]"

        with open(file_path, "r") as file:
            content = file.read()

            match split_size > -1, split_criteria:
                case True, TextSplitCriteria.LENGTH:
                    if len(content) > split_size:
                        content = content[:split_size] + truncated_message
                case True, TextSplitCriteria.TOKEN_COUNT:
                    text_splitter = TokenTextSplitter(
                        chunk_size=MAX_INPUT_TOKENS, chunk_overlap=0
                    )
                    texts = text_splitter.split_text(content)
                    content = texts[0] + (
                        truncated_message if len(texts) > 1 else ""
                    )
        return content
    except Exception as e:
        if ignore_errors:
            Logger.warning(
                f"Error reading file {file_path}: {str(e)}", exc_info=True
            )
            return ""
        raise e
