import asyncio
import os
from pathlib import Path
from typing import Generator

import faiss
from langchain.docstore import InMemoryDocstore
from langchain.schema import Document
from langchain_community.vectorstores import FAISS
from langchain_core.retrievers import BaseRetriever
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from apps.git import ChangeMode, GitRepository
from apps.settings import CONFIG, INDEX_DIR, MAX_EMBEDDING_TOKENS, Logger
from apps.utils import count_tokens, filter_files

_index_lock = asyncio.Lock()
_cache = {}


async def get_retriever(git_repo: GitRepository) -> BaseRetriever:
    async with _index_lock:
        if _cache.get(git_repo.repository):
            return _cache[git_repo.repository]
        vector_store_manager = VectorStoreManager(git_repo)
        faiss = await vector_store_manager.get_vector_store()
        faiss_retriever = faiss.as_retriever(
            search_type="mmr", search_kwargs={"k": 12, "lambda_mult": 0.25}
        )
        _cache[git_repo.repository] = faiss_retriever
        return faiss_retriever


class VectorStoreManager:
    def __init__(self, git_repo: GitRepository):
        self.index_name = "index"
        self.git_repo = git_repo
        self.folder_path = os.path.join(
            INDEX_DIR, git_repo.owner, git_repo.repo
        )
        self.commit_hash_path = os.path.join(self.folder_path, "commit_hash")
        self.embedding = OpenAIEmbeddings(
            model=CONFIG["embedder"]["model"],
            dimensions=CONFIG["embedder"]["dimensions"],
        )
        self.document_loader = DocumentLoader()

    async def get_vector_store(self) -> FAISS:
        vector_store = self._load_from_disk() or self._create_vector_store()
        return vector_store

    def _load_from_disk(self) -> FAISS | None:
        try:
            vector_store = FAISS.load_local(
                folder_path=self.folder_path,
                index_name=self.index_name,
                embeddings=self.embedding,
                allow_dangerous_deserialization=True,
            )
            if updated := self._update_vector_store(vector_store):
                self._save_to_disk(vector_store)
            return vector_store
        except Exception as e:
            Logger.error(f"Failed to load vector store from disk: {e}")
            return None

    def _save_to_disk(self, vector_store: FAISS) -> None:
        vector_store.save_local(
            folder_path=self.folder_path, index_name=self.index_name
        )
        open(self.commit_hash_path, "w").write(self.git_repo.commit_hash)

    def _create_vector_store(self) -> FAISS:
        Logger.info(f"Creating FAISS index for {self.git_repo.repository}...")
        index = faiss.IndexFlatL2(self.embedding.dimensions)
        vector_store = FAISS(
            embedding_function=self.embedding,
            index=index,
            docstore=InMemoryDocstore(),
            index_to_docstore_id={},
        )
        for docs in self.document_loader.load_documents(
            self.git_repo.repo_path
        ):
            vector_store.add_documents(docs)
        return vector_store

    def _get_commit_hash(self) -> str:
        if os.path.exists(self.commit_hash_path):
            with open(self.commit_hash_path) as f:
                return f.read().strip()
        return ""

    def _update_vector_store(self, vector_store: FAISS) -> bool:
        commit_hash = self._get_commit_hash()
        if self.git_repo.commit_hash == commit_hash:
            return False  # No changes detected
        Logger.info(
            f"Commit hash changed for {self.git_repo.repository}. "
            "{self.git_repo.commit_hash} -> {new_commit_hash}"
        )
        updated = False
        for mode, file_path in self.git_repo.list_diff_files(commit_hash):
            updated = True
            load = mode in [ChangeMode.ADDED, ChangeMode.MODIFIED]
            delete = mode in [ChangeMode.DELETED, ChangeMode.MODIFIED]

            try:
                if delete:
                    # Delete modified/deleted files from the index
                    chunk = 0
                    while True:
                        id = f"{file_path}_{chunk}"
                        try:
                            if vector_store.delete(ids=[id]):
                                Logger.debug(f"Deleted {id} from index.")
                                chunk += 1
                            else:
                                break
                        except Exception as e:
                            break
                if load:
                    documents = self.document_loader.load_documents_from_file(
                        repo_root=self.git_repo.repo_path,
                        file_path=file_path,
                    )
                    if len(documents) > 0:
                        # Add modified/added files to the index
                        vector_store.add_documents(documents=documents)
                        Logger.debug(
                            f"Added {file_path} into index. "
                            f"({len(documents)} documents)"
                        )
            except Exception as e:
                Logger.warning(f"Error loading file {file_path}: {e}")
        return updated


class DocumentLoader:
    def load_documents_from_file(
        self, repo_root: Path, file_path: Path
    ) -> list[Document]:
        documents = []
        with open(repo_root / file_path) as f:
            try:
                ext = os.path.splitext(file_path)[1]
                is_code = (
                    ext == ""
                    or ext in CONFIG["file_filters"]["code_extensions"]
                )

                content = f.read()
                token_count = count_tokens(content)
                if not is_code and token_count > MAX_EMBEDDING_TOKENS:
                    Logger.warning(f"File {file_path} exceeds max token limit.")
                    return documents

                chunk_size = CONFIG["embedder"]["chunk_size"]
                chunk_overlap = CONFIG["embedder"]["chunk_overlap"]
                code_splitter = RecursiveCharacterTextSplitter.from_language(
                    language=get_language(ext),
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
                chunks = code_splitter.split_text(content)

                for i, chunk in enumerate(chunks):
                    id = f"{file_path}_{i}"
                    doc = Document(
                        id=id,
                        page_content=chunk,
                        metadata={
                            "file_path": file_path,
                            "type": os.path.splitext(file_path)[1][1:],
                            "title": file_path,
                            "token_count": token_count,
                            "chunk": i,
                        },
                    )
                    documents.append(doc)
                return documents
            except Exception as e:
                Logger.warning(f"Error loading file {file_path}: {e}")
                return documents

    def load_documents(self, repo_path: Path) -> Generator[list[Document]]:
        code_extensions = CONFIG["file_filters"]["code_extensions"]
        doc_extensions = CONFIG["file_filters"]["doc_extensions"]
        excluded_dirs = CONFIG["file_filters"]["excluded_dirs"]
        excluded_files = CONFIG["file_filters"]["excluded_files"]

        extensions = code_extensions + doc_extensions

        for file in filter_files(
            str(repo_path), extensions, excluded_dirs, excluded_files
        ):
            file_path = Path(os.path.relpath(file, repo_path))
            docs = self.load_documents_from_file(
                repo_root=repo_path, file_path=file_path
            )
            if len(docs) > 0:
                yield docs


def get_language(ext: str) -> Language:
    languages = {
        ".py": Language.PYTHON,
        ".js": Language.JS,
        ".ts": Language.TS,
        ".java": Language.JAVA,
        ".cpp": Language.CPP,
        ".c": Language.C,
        ".go": Language.GO,
        ".rs": Language.RUST,
        ".jsx": Language.JS,
        ".tsx": Language.TS,
        ".html": Language.HTML,
        ".php": Language.PHP,
        ".swift": Language.SWIFT,
        ".cs": Language.CSHARP,
        ".kt": Language.KOTLIN,
    }
    return languages.get(ext, Language.C)
