import os
import time
import json
import hashlib
from typing import Callable
from openai import OpenAI
# from importlib.util import find_spec
# from pathlib import Path

from dotenv import load_dotenv, main
from llama_index.core import (
        Settings, 
        SimpleDirectoryReader, 
        VectorStoreIndex, 
        StorageContext,
        load_index_from_storage
)
from llama_index.core.node_parser import (
        SentenceSplitter, 
        MarkdownNodeParser, 
        MarkdownElementNodeParser
)
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from llama_index.llms.openai_like import OpenAILike
from llama_index.readers.file import DocxReader, PDFReader
from qwen_reranker import QwenRerankPostprocessor

load_dotenv()

# Match file in `docs/` with the specified name.
MANIFEST_PATH = "trad_rag/manifest/manifest.json"
PERSIST_DIR = "trad_rag/persist"
DOC_DIR = "docs"

DOC_1 = "銆愬凡瀹℃煡銆戯紙214鍙凤級娴欐睙鍐滃晢涓庣Щ鍔ㄦ禉姹熷叕鍙搁泦鍥㈠浐璇濅笟鍔″崗璁?淇4(1)_clean.docx"
DOC_2 = "銆愬凡瀹℃煡銆戯紙528鍙凤級2026骞磋嚦2028骞磋吹瀹惧尰鐤楁湇鍔″悎浣滃崗璁?閭甸€稿か鍖婚櫌_clean.docx"
DOC_3 = "鍙嶉0730-銆愬凡瀹℃煡銆戯紙190鍙凤級浜掕仈缃戠被绯荤粺CDN鍔犻€熸湇鍔★紙涓夊勾锛夐噰璐悎鍚孒T-ZRUB-2025-07-01-08-C002.docx"
DOC_4 = "Dynamic TOC Extraction Strategy.md"

DOC_PATH_1 = os.path.join(DOC_DIR, DOC_1)
DOC_PATH_2 = os.path.join(DOC_DIR, DOC_2)
DOC_PATH_3 = os.path.join(DOC_DIR, DOC_3)
DOC_PATH_4 = os.path.join(DOC_DIR, DOC_4)

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_NAME = os.getenv("LLM_NAME")

EMBED_API_KEY = os.getenv("EMBED_API_KEY")
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL")
EMBED_NAME = os.getenv("EMBED_NAME")

RERANK_API_KEY = os.getenv("RERANK_API_KEY")
RERANK_BASE_URL = os.getenv("RERANK_BASE_URL")
RERANK_NAME = os.getenv("RERANK_NAME")

# QUERY = "审核一下这份合同金额大小写是否有问题。你只能返回存在问题的内容。如果没有问题，请返回：没有发现金额大小写问题。"
QUERY = "总结一下该文档的内容。"

# trad_rag
class TRAD_RAG:
    def __init__(
            self, 
            query: str, 
            doc_path: str,
            manifest_path: str,
            persist_dir: str,
            llm_api_key: str, 
            llm_base_url: str,
            llm_name: str,
            embed_api_key: str,
            embed_base_url: str,
            embed_name: str, 
            rerank_api_key: str, 
            rerank_base_url: str,
            rerank_name: str
        ) -> None:

        self.query = query
        self.doc_path = doc_path
        self.manifest_path = manifest_path
        self.persist_dir = persist_dir
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_name = llm_name
        self.embed_api_key = embed_api_key
        self.embed_base_url = embed_base_url
        self.embed_name = embed_name
        self.reranker_api_key = rerank_api_key
        self.rerank_base_url = rerank_base_url
        self.rerank_name = rerank_name
        self.reranker = QwenRerankPostprocessor(
            api_key=self.reranker_api_key,
            base_url=self.rerank_base_url,
            model=self.rerank_name, 
            top_n=3, 
            instruct="Given a contract review query, retrieve relevant passages that answer the query."
        )
        
    # util (read file hash)
    def file_sha256(self, doc_path: str) -> str:
        h = hashlib.sha256()
        with open(doc_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # util (check file path)
    def resolve_input_file(self, doc_path: str) -> list:
        if not os.path.isfile(doc_path):
            raise FileNotFoundError(f"{doc_path} is not a valid file path.")
        input_files = [doc_path]
        return input_files

    # util (extract file content based on file type)
    def build_pdf_and_docx_extractor(self, input_files: list) -> dict[str, object]:
        suffixes = {os.path.splitext(path)[1].lower() for path in input_files}
        if not suffixes:
            return {}

        file_extractor = {}
        if ".pdf" in suffixes:
            file_extractor[".pdf"] = PDFReader()
        if ".docx" in suffixes:
            file_extractor[".docx"] = DocxReader()
        return file_extractor

    # query rewrite
    def query_rewrite(self, query: str) -> str:
        client = OpenAI(
            api_key=self.llm_api_key,
            base_url=self.llm_base_url
        )
        agent = client.chat.completions.create(
            model=self.llm_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant for rephrasing the question on a contract. You will always answer in Simplified Chinese.",
                },
                {
                    "role": "user",
                    "content": f"""
                    Question: {query}. 
                    Please rephrase this query to be more specific and clear for the contract. 
                    Please only return the rephrased question without any explanation.
                    """,
                },
            ],
        )
        return agent.choices[0].message.content

    # load/parse document [resolve_input_file, build_pdf_and_docx_extractor]
    def load_documents(self, doc_path: str) -> list[object]:
        suffix = os.path.splitext(doc_path)[-1]
        if suffix in (".docx", ".pdf"):
            file_extractor = self.build_pdf_and_docx_extractor(input_files)
        else: 
            file_extractor = {}
        
        input_files = self.resolve_input_file(doc_path)

        return SimpleDirectoryReader(
            input_files=[str(path) for path in input_files],
            file_extractor=file_extractor,
        ).load_data()

    # chunk document
    def chunk_document(self, documents: list) -> list: 
        suffix = os.path.splitext(self.doc_path)[-1] # noticeable point
        if suffix == ".md":
            markdown_parser = MarkdownNodeParser.from_defaults(
                header_path_separator=" / "
            )
            section_nodes = markdown_parser.get_nodes_from_documents(documents)
            element_parser = MarkdownElementNodeParser(
                llm=Settings.llm, 
                show_progress=False
            )

            nodes = []
            for node in section_nodes:
                nodes.extend(element_parser.get_nodes_from_node(node))
            return nodes
        
        else:
            splitter = SentenceSplitter(chunk_size=512, chunk_overlap=100)
            nodes = splitter.get_nodes_from_documents(documents)
            return nodes

    # index document [load_documents, chunk_document]
    def index_document(self) -> object:
        # manifest looks like: 
        current_meta = {
            "doc_hash": self.file_sha256(self.doc_path), 
            "chunk_size": 512,
            "chunk_overlap": 100,
            "embedding_model": self.embed_name
        }

        # if manifest exists and persist dir exists, then load index from storage, else load and chunk document, then index document, finally persist index to storage
        if os.path.exists(self.manifest_path) and os.path.exists(self.persist_dir):
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                saved_meta = json.load(f)
            
            if saved_meta == current_meta:
                # load index from storage (no doc loading and chunking)
                storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
                index = load_index_from_storage(storage_context)
                return index # stop here if loaded index successfully

        # don't add else here
        # build a new index when cache is missing or manifest metadata changed
        documents = self.load_documents(self.doc_path) # list -> extract -> load
        print(f"Loaded {len(documents)} documents.")

        # chunk document
        # index = VectorStoreIndex.from_documents(documents) # index
        nodes = self.chunk_document(documents) # chunk
        # index document
        index = VectorStoreIndex(nodes) # index

        # create persist dir and manifest dir if not exist
        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        os.makedirs(self.persist_dir, exist_ok=True)
        # persist index to storage
        index.storage_context.persist(persist_dir=self.persist_dir)
        with open(self.manifest_path, "w", encoding="utf-8") as f: 
            json.dump(current_meta, f, ensure_ascii=False, indent=2)
        
        return index
    
    # retrieve / rerank docs inside of document
    def retrieve(self, index: object, query: str) -> str:
        retriever = index.as_retriever(similarity_top_k=5)
        reranker = self.reranker

        query_engine = RetrieverQueryEngine.from_args(
            retriever=retriever,
            node_postprocessors=[reranker]
        )
        response = query_engine.query(query)

        return response

    
    def main(self) -> str:
        Settings.llm = OpenAILike(
            model=self.llm_name,
            api_key=self.llm_api_key,
            api_base=self.llm_base_url,
            is_chat_model=True,
            is_function_calling_model=True
        )

        Settings.embed_model = OpenAILikeEmbedding(
            model_name=self.embed_name,
            api_key=self.embed_api_key,
            api_base=self.embed_base_url,
        )

        # start time count
        start = time.time()

        # obtain document index
        index = self.index_document()

        # rewrite query and query engine
        QUERY_REWRITE = self.query_rewrite(self.query)
        # print(f"Rewritten Query: {QUERY_REWRITE}")
        response = self.retrieve(
            index, 
            QUERY_REWRITE
        ) 
        
        # finish time count
        elapsed = time.time() - start
        print(f"Time taken: {elapsed:.2f} seconds")

        return response


if __name__ == "__main__":

    TRAD_RAG_ins = TRAD_RAG(
        query=QUERY,
        doc_path=DOC_PATH_4,
        manifest_path=MANIFEST_PATH,
        persist_dir=PERSIST_DIR,
        llm_api_key=LLM_API_KEY,
        llm_base_url=LLM_BASE_URL,
        llm_name=LLM_NAME,
        embed_name=EMBED_NAME,
        embed_api_key=EMBED_API_KEY,
        embed_base_url=EMBED_BASE_URL, 
        rerank_api_key=RERANK_API_KEY,
        rerank_base_url=RERANK_BASE_URL,
        rerank_name=RERANK_NAME
    )

    response = TRAD_RAG_ins.main()
    print(f"Response: {response}")
