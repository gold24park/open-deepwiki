import argparse
import asyncio
from typing import Literal

from apps.context import ContextBuilder
from apps.pipeline import Pipeline
from apps.settings import GITHUB_ACCESS_TOKEN
from apps.wiki_file import Download, SkippedOperationError, Upload
from apps.wiki_index import GenerateIndex
from apps.wiki_page import GeneratePages
from apps.wiki_structure import GenerateStructure

type ExitCode = Literal[0, 1, 100]


async def run(repository: str, pat: str, branch: str) -> ExitCode:
    context = ContextBuilder.from_file("wiki_config.yaml", repository, pat)

    pipeline = (
        Pipeline.with_context(context)
        .register(Download)
        .register(GenerateStructure)
        .register(GeneratePages)
        .register(GenerateIndex)
        .register(Upload)
    )

    result = await pipeline.execute(branch)

    match result.status:
        case "failure" if isinstance(result.error, SkippedOperationError):
            exit_code = 100
        case "failure":
            exit_code = 1
        case _:
            exit_code = 0
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate Wiki for a GitHub repository."
    )

    parser.add_argument(
        "repository", type=str, help="GitHub repository owner/name."
    )
    parser.add_argument(
        "--branch", type=str, help="Branch to generate wiki from.", default=None
    )
    parser.add_argument(
        "--pat",
        type=str,
        help="GitHub Personal Access Token.",
        default=GITHUB_ACCESS_TOKEN,
    )

    args = parser.parse_args()
    exit_code = asyncio.run(
        run(
            repository=args.repository,
            pat=args.pat,
            branch=args.branch,
        )
    )
    exit(exit_code)
