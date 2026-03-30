"""
LlamaIndex-based RAG engine for contract document retrieval.

Provides vector-based retrieval with reranking as an alternative to
PageIndex tree-based search.
"""
import os
import json
import hashlib
import tempfile

from llama_index.core import (
    Settings,
    SimpleDirectoryReader,
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage,
)
from llama_index.core.node_parser import (
    SentenceSplitter,
    MarkdownNodeParser,
    MarkdownElementNodeParser,
)
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from llama_index.llms.openai_like import OpenAILike
from llama_index.readers.file import DocxReader, PDFReader

from tools.retrieval.llamaindex.qwen_reranker import QwenRerankPostprocessor


class LlamaIndexRAG:
    """Vector-based RAG with embedding + reranking.

    Can be used standalone or wrapped as MCP tools.
    """

    def __init__(
        self,
        *,
        persist_dir: str,
        manifest_path: str,
        llm_api_key: str,
        llm_base_url: str,
        llm_name: str,
        embed_api_key: str,
        embed_base_url: str,
        embed_name: str,
        rerank_api_key: str = None,
        rerank_base_url: str = None,
        rerank_name: str = None,
        similarity_top_k: int = 5,
        rerank_top_n: int = 3,
    ) -> None:
        self.persist_dir = persist_dir
        self.manifest_path = manifest_path
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_name = llm_name
        self.embed_api_key = embed_api_key
        self.embed_base_url = embed_base_url
        self.embed_name = embed_name
        self.similarity_top_k = similarity_top_k

        # Configure LlamaIndex global settings
        Settings.llm = OpenAILike(
            model=llm_name,
            api_key=llm_api_key,
            api_base=llm_base_url,
            is_chat_model=True,
            is_function_calling_model=True,
        )
        Settings.embed_model = OpenAILikeEmbedding(
            model_name=embed_name,
            api_key=embed_api_key,
            api_base=embed_base_url,
        )

        self.reranker = None
        if rerank_api_key and rerank_name:
            self.reranker = QwenRerankPostprocessor(
                api_key=rerank_api_key,
                base_url=rerank_base_url or embed_base_url,
                model=rerank_name,
                top_n=rerank_top_n,
                instruct="Given a contract review query, retrieve relevant passages that answer the query.",
            )

        self._index = None
        self._loaded_doc_hash = None

    def _cache_locations(self) -> list[tuple[str, str, str]]:
        """Return current and backward-compatible cache locations."""
        locations = [(self.persist_dir, self.manifest_path, "loaded_from_cache")]

        persist_parent = os.path.dirname(self.persist_dir.rstrip(os.sep))
        manifest_parent = os.path.dirname(self.manifest_path)
        legacy_persist_dir = os.path.join(persist_parent, "persist")
        legacy_manifest_path = os.path.join(manifest_parent, "manifest", "manifest.json")

        if (
            legacy_persist_dir != self.persist_dir
            or legacy_manifest_path != self.manifest_path
        ):
            locations.append(
                (legacy_persist_dir, legacy_manifest_path, "loaded_from_legacy_cache")
            )

        return locations

    def _load_cached_index(self, current_meta: dict) -> str | None:
        """Load an index from disk when the persisted metadata matches."""
        for persist_dir, manifest_path, status in self._cache_locations():
            if not (os.path.exists(manifest_path) and os.path.exists(persist_dir)):
                continue

            with open(manifest_path, "r", encoding="utf-8") as f:
                saved_meta = json.load(f)

            if saved_meta != current_meta:
                continue

            storage_context = StorageContext.from_defaults(persist_dir=persist_dir)
            self._index = load_index_from_storage(storage_context)
            self._loaded_doc_hash = current_meta["doc_hash"]
            return json.dumps({"status": status, **current_meta})

        return None

    # ── Index building ─────────────────────────────────────

    @staticmethod
    def _file_sha256(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def build_index_from_file(self, doc_path: str) -> str:
        """Build (or load cached) vector index from a document file.

        Returns:
            A JSON string with index metadata (persist_dir, doc_hash, etc.)
        """
        suffix = os.path.splitext(doc_path)[-1].lower()

        current_meta = {
            "doc_hash": self._file_sha256(doc_path),
            "chunk_size": 512,
            "chunk_overlap": 100,
            "embedding_model": self.embed_name,
        }

        if self._index is not None and self._loaded_doc_hash == current_meta["doc_hash"]:
            return json.dumps({"status": "already_loaded", **current_meta})

        cached_result = self._load_cached_index(current_meta)
        if cached_result is not None:
            return cached_result

        # Build new index
        file_extractor = {}
        if suffix == ".pdf":
            file_extractor[".pdf"] = PDFReader()
        elif suffix == ".docx":
            file_extractor[".docx"] = DocxReader()

        # Load
        documents = SimpleDirectoryReader(
            input_files=[doc_path],
            file_extractor=file_extractor,
        ).load_data()

        # Chunk
        if suffix == ".md":
            markdown_parser = MarkdownNodeParser.from_defaults(header_path_separator=" / ")
            section_nodes = markdown_parser.get_nodes_from_documents(documents)
            element_parser = MarkdownElementNodeParser(llm=Settings.llm, show_progress=False)
            nodes = []
            for node in section_nodes:
                nodes.extend(element_parser.get_nodes_from_node(node))
        else:
            splitter = SentenceSplitter(chunk_size=512, chunk_overlap=100)
            nodes = splitter.get_nodes_from_documents(documents)

        self._index = VectorStoreIndex(nodes)
        self._loaded_doc_hash = current_meta["doc_hash"]

        # Persist
        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        os.makedirs(self.persist_dir, exist_ok=True)
        self._index.storage_context.persist(persist_dir=self.persist_dir)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(current_meta, f, ensure_ascii=False, indent=2)

        return json.dumps({"status": "built_new_index", "num_nodes": len(nodes), **current_meta})

    def build_index_from_markdown(self, markdown_content: str) -> str:
        """Build vector index from raw markdown content (for MCP integration).

        Returns:
            A JSON string with index metadata.
        """
        content_hash = hashlib.sha256(markdown_content.encode()).hexdigest()
        current_meta = {
            "doc_hash": content_hash,
            "chunk_size": 512,
            "chunk_overlap": 100,
            "embedding_model": self.embed_name,
        }

        if self._index is not None and self._loaded_doc_hash == current_meta["doc_hash"]:
            return json.dumps({"status": "already_loaded", **current_meta})

        cached_result = self._load_cached_index(current_meta)
        if cached_result is not None:
            return cached_result

        # Write to temp file for SimpleDirectoryReader
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(markdown_content)
            tmp_path = f.name

        try:
            documents = SimpleDirectoryReader(input_files=[tmp_path]).load_data()

            markdown_parser = MarkdownNodeParser.from_defaults(header_path_separator=" / ")
            section_nodes = markdown_parser.get_nodes_from_documents(documents)
            element_parser = MarkdownElementNodeParser(llm=Settings.llm, show_progress=False)
            nodes = []
            for node in section_nodes:
                nodes.extend(element_parser.get_nodes_from_node(node))

            self._index = VectorStoreIndex(nodes)
            self._loaded_doc_hash = current_meta["doc_hash"]

            os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
            os.makedirs(self.persist_dir, exist_ok=True)
            self._index.storage_context.persist(persist_dir=self.persist_dir)
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(current_meta, f, ensure_ascii=False, indent=2)
        finally:
            os.unlink(tmp_path)

        return json.dumps({"status": "built_new_index", "num_nodes": len(nodes), **current_meta})

    # ── Search ─────────────────────────────────────────────

    def search(self, query: str) -> str:
        """Search the loaded index. Returns retrieved text with source info."""
        if self._index is None:
            return "Error: No index loaded. Call build_index first."

        retriever = self._index.as_retriever(similarity_top_k=self.similarity_top_k)
        postprocessors = [self.reranker] if self.reranker else []

        query_engine = RetrieverQueryEngine.from_args(
            retriever=retriever,
            node_postprocessors=postprocessors,
        )
        response = query_engine.query(query)

        # Format as structured text for downstream agents
        parts = []
        for i, source_node in enumerate(response.source_nodes, 1):
            score = getattr(source_node, "score", None)
            text = source_node.get_content()
            header = f"## 检索结果 {i}"
            if score is not None:
                header += f" (相关度: {score:.3f})"
            parts.append(f"{header}\n{text}")

        return "\n\n---\n\n".join(parts) if parts else "No relevant sections found."
