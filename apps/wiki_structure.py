import json

from apps.agent import complete_chat
from apps.context import Context
from apps.model import WikiStructure
from apps.pipeline import Operation, Result
from apps.settings import CONFIG


class _Operation(Operation[None, WikiStructure, Context]):
    async def invoke(
        self, context: Context, input: None = None
    ) -> Result[WikiStructure]:
        try:
            structure = await _create_wiki_structure(context)
            return Result.success(structure)
        except Exception as e:
            return Result.failure(e)


GenerateStructure = _Operation()


async def _create_wiki_structure(
    context: Context,
) -> WikiStructure:
    file_tree = context.git_repo.get_file_tree()

    most_updated_files = context.git_repo.get_most_updated_files(
        since="6 months ago",
        top_n=10,
        filter_exists=True,
    )

    hint_obj = {
        "tutorial": context.config.tutorial,
        "how_to": context.config.how_to,
        "reference": context.config.reference,
        "explanation": context.config.explanation,
    }
    hint = json.dumps(hint_obj, indent=2, ensure_ascii=False)

    prompt = open(CONFIG["structure_generation"]["prompt"]).read()

    model_config = CONFIG["structure_generation"]
    model_config["model"] = context.config.model or model_config["model"]

    return await complete_chat(
        prompt=prompt.format(
            repository=context.git_repo.repository,
            file_tree=file_tree,
            most_updated_files=most_updated_files,
            hint=hint,
            language=context.config.language,
        ),
        repo=context.git_repo,
        model_config=model_config,
        response_format=WikiStructure,
    )
