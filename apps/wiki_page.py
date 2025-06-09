import asyncio
from typing import Awaitable, Callable, ParamSpec, TypeVar

from cleantext import clean

from apps.agent import complete_chat
from apps.context import Context
from apps.model import WikiPage, WikiStructure
from apps.pipeline import Operation, Result
from apps.settings import IS_TEST, Logger
from apps.utils import CONFIG, normalize_path

P = ParamSpec("P")
T = TypeVar("T")


class _Operation(Operation[WikiStructure, WikiStructure, Context]):
    async def invoke(
        self, context: Context, input: WikiStructure
    ) -> Result[WikiStructure]:
        try:
            # 테스트 모드일경우 1페이지만 생성합니다.
            max_pages = 1 if IS_TEST else len(input.pages)

            # 한꺼번에 3개의 페이지를 생성할 수 있도록 제한합니다.
            semaphore = asyncio.Semaphore(3)

            tasks = []
            for page in input.pages[:max_pages]:
                task = asyncio.create_task(
                    limited_parallel(
                        semaphore,
                        _create_wiki_page,
                        context=context,
                        structure=input,
                        page=page,
                    )
                )
                tasks.append(task)

            Logger.info(f"Generating {len(tasks)} wiki pages...")
            await asyncio.gather(*tasks)

            return Result.success(input)
        except Exception as e:
            return Result.failure(e)

    async def rollback(self, context: Context, input: WikiStructure):
        context.wiki_repo.cleanup()


GeneratePages = _Operation()


async def _create_wiki_page(
    context: Context,
    structure: WikiStructure,
    page: WikiPage,
):
    Logger.info(f"Generating wiki page...{page.title}")
    relevant_pages = [
        "[{title}]({path})".format(
            title=p.title,
            path=p.path,
        )
        for p in structure.pages
        if p.path in page.relevant_page_paths
    ]

    prompt = open(CONFIG["page_generation"]["prompt"]).read()

    model_config = CONFIG["page_generation"]
    model_config["model"] = context.config.model or model_config["model"]

    content = await complete_chat(
        prompt.format(
            repository=context.git_repo.repository,
            title=page.title,
            description=page.description,
            branch=context.git_repo.branch,
            path=page.path,
            relevant_files="\n".join(page.relevant_files),
            relevant_pages="\n".join(relevant_pages),
            language=context.config.language,
        ),
        repo=context.git_repo,
        model_config=model_config,
    )

    file_path = context.wiki_repo.wiki_path / normalize_path(page.path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w") as file:
        file.write(content)


async def limited_parallel(
    semaphore: asyncio.Semaphore,
    async_func: Callable[P, Awaitable[T]],
    *args: P.args,
    **kwargs: P.kwargs,
):
    async with semaphore:
        await async_func(*args, **kwargs)


def generate_id(text: str) -> str:
    text = text.replace(" ", "-")
    return clean(
        text,
        lower=True,
        no_urls=True,
        no_currency_symbols=True,
        no_emoji=True,
    )
