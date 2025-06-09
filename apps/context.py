import msgspec

from apps.git import GitRepository, Path, WikiRepository
from apps.model import WikiConfiguration
from apps.settings import Logger
from apps.utils import parse_duration


class Context:
    def __init__(self, git_repo: GitRepository, config: WikiConfiguration):
        self.git_repo = git_repo
        self.config = config
        self.wiki_repo = WikiRepository(git_repo, config)


class ContextBuilder:
    @staticmethod
    def from_file(
        filepath: str | Path, repository: str, pat: str | None
    ) -> Context:
        config = WikiConfiguration()

        try:
            data = msgspec.yaml.decode(
                open(filepath, "rb").read(),
                type=dict,
                strict=False,
            )
            if skip := data.get("skip"):
                data["skip"] = parse_duration(skip)
            config = msgspec.convert(data, type=WikiConfiguration)
        except Exception as e:
            Logger.warning(f"Error loading wiki config: {e}")

        return ContextBuilder.from_config(config, repository, pat)

    @staticmethod
    def from_data(
        config_data: dict, repository: str, pat: str | None
    ) -> Context:
        config = msgspec.convert(
            config_data,
            type=WikiConfiguration,
            strict=False,
        )
        return ContextBuilder.from_config(config, repository, pat)

    @staticmethod
    def from_config(
        config: WikiConfiguration, repository: str, pat: str | None
    ) -> Context:
        git_repo = GitRepository(
            repository=repository,
            pat=pat,
        )

        return Context(
            git_repo=git_repo,
            config=config,
        )
