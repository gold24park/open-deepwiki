from directory_tree import DisplayTree

from apps.agent import complete_chat
from apps.context import Context
from apps.pipeline import Operation, Result
from apps.settings import CONFIG
from apps.wiki_page import WikiStructure


class _Operation(Operation[WikiStructure, None, Context]):
    async def invoke(
        self, context: Context, input: WikiStructure
    ) -> Result[None]:
        try:
            await _create_wiki_index(context, input)
            return Result.success()
        except Exception as e:
            return Result.failure(e)

    async def rollback(self, context: Context, input: WikiStructure):
        context.wiki_repo.cleanup()


GenerateIndex = _Operation()


async def _create_wiki_index(
    context: Context,
    structure: WikiStructure,
):
    filetree = (
        DisplayTree(
            dirPath=context.wiki_repo.wiki_path,
            stringRep=True,
        )
        or ""
    )
    filetree = filetree.replace(f"{context.git_repo.repo}/", "/")

    prompt = open(CONFIG["index_generation"]["prompt"]).read()

    model_config = CONFIG["index_generation"]
    model_config["model"] = context.config.model or model_config["model"]
    content = await complete_chat(
        prompt.format(
            repo=context.git_repo.repo,
            filetree=filetree,
            structure=structure.model_dump_json(indent=2),
            language=context.config.language,
        ),
        repo=context.git_repo,
        model_config=model_config,
    )

    path = context.wiki_repo.wiki_path / "README.md"
    with open(path, "w") as file:
        file.write(content)
