from datetime import datetime

from apps.context import Context
from apps.pipeline import Operation, Result
from apps.settings import IS_TEST, Logger


class SkippedOperationError(Exception):
    pass


class _DownloadOperation(Operation[str, None, Context]):
    async def invoke(self, context: Context, input: str) -> Result[None]:
        try:
            context.git_repo.download(
                branch=input, ignore_patterns=context.config.ignore_patterns
            )
            # 마지막 커밋이후 interval이 지난 경우에만 Wiki를 생성합니다.
            now = datetime.now()
            commit_time = context.wiki_repo.get_last_commit_time()

            is_up_to_date = (
                commit_time and now - commit_time < context.config.skip
            )

            if is_up_to_date and not IS_TEST:
                raise SkippedOperationError(
                    f"Wiki is up to date. Skipping generation. Last commit: {commit_time}"
                )
            return Result.success()
        except Exception as e:
            Logger.error(f"Failed to download repository: {e}")
            return Result.failure(e)


Download = _DownloadOperation()


class _UploadOperation(Operation[str, None, Context]):
    async def invoke(self, context: Context, input: str) -> Result[None]:
        try:
            context.wiki_repo.upload()
            return Result.success()
        except Exception as e:
            return Result.failure(e)

    async def rollback(self, context: Context, input: str):
        context.wiki_repo.cleanup()


Upload = _UploadOperation()
