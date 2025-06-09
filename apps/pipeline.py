from abc import ABC, abstractmethod
from typing import Any, Generic, Literal, TypeVar

import msgspec

from apps.model import WikiStructure

T = TypeVar("T")
U = TypeVar("U")
PT = TypeVar("PT")
PU = TypeVar("PU")
CTX = TypeVar("CTX")


class Result(Generic[T], msgspec.Struct):
    status: Literal["success", "failure"]
    error: Exception | None = None
    value: T | None = None

    @staticmethod
    def success(value: T = None) -> "Result[T]":
        return Result(status="success", value=value, error=None)

    @staticmethod
    def failure(error: Exception) -> "Result[T]":
        return Result(status="failure", value=None, error=error)


class Operation(Generic[T, U, CTX], ABC):
    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def invoke(self, context: CTX, input: T) -> Result[U]: ...

    async def rollback(self, context: CTX, input: T):
        """Rollback operation if needed."""
        pass


class Pipeline(Generic[CTX]):
    def __init__(self, context: CTX) -> None:
        self.context: CTX = context

    @staticmethod
    def with_context(context: T) -> "Pipeline[T]":
        return Pipeline[T](context)

    def register(
        self, operation: Operation[T, U, CTX]
    ) -> "_Pipeline[T, U, CTX]":
        pipeline = _Pipeline[T, U, CTX](self.context)
        pipeline.operations = [operation]
        return pipeline


class _Pipeline(Generic[PT, PU, CTX]):
    def __init__(self, context: CTX) -> None:
        self.context = context
        self.operations: list[Operation] = []

    def register(
        self, operation: Operation[T, U, CTX]
    ) -> "_Pipeline[PT, U, CTX]":
        pipeline = _Pipeline[PT, U, CTX](self.context)
        pipeline.operations = self.operations + [operation]
        return pipeline

    async def execute(self, param: PT = None) -> Result[PU]:
        input: Any = param

        result: Result[Any] = Result(status="success")
        for operation in self.operations:
            result = await operation.invoke(context=self.context, input=input)
            if result.status == "failure":
                await operation.rollback(context=self.context, input=input)
                return result
            input = result.value
        return result


if __name__ == "__main__":

    class TestContext(msgspec.Struct):
        name: str = "TestContext"

    class StructureOperation(Operation[str, WikiStructure, TestContext]):
        async def invoke(
            self, context: TestContext, input: str
        ) -> Result[WikiStructure]:
            print("Generating wiki structure...")
            print(f"Input: {input}")
            return Result(
                status="success",
                value=WikiStructure(title=input, pages=[]),
                error=None,
            )

    class PageOperation(Operation[WikiStructure, None, TestContext]):
        async def invoke(
            self, context: TestContext, input: WikiStructure
        ) -> Result[None]:
            print("Creating wiki pages based on structure...")
            print(f"Structure title: {input.title}")
            return Result(
                status="success",
                value=None,
                error=None,
            )

    async def run():
        # pipeline = (
        #     Pipeline().register(StructureOperation()).register(PageOperation())
        # )
        pipeline = (
            Pipeline.with_context(TestContext())
            .register(StructureOperation())
            .register(PageOperation())
        )

        result = await pipeline.execute("한글공부")
        if result:
            print("Pipeline executed successfully.")
        else:
            print("Pipeline execution failed.")
