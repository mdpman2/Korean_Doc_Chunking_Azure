from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import AzureOpenAIEmbeddings
import os

def optimized_korean_chunking(markdown_text):
    """
    1단계: Markdown Header 기준으로 의미 단위 분리
    2단계: Azure OpenAI Embedding을 이용한 Semantic Chunking
    """

    # 1. 구조적 분할 (Header 기준)
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]

    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    header_splits = markdown_splitter.split_text(markdown_text)

    # 2. 의미론적 분할 (Semantic Chunking)
    # Azure OpenAI Embedding 모델 초기화
    embeddings = AzureOpenAIEmbeddings(
        azure_deployment=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_KEY")
    )

    # Semantic Chunker 초기화
    # percentile, standard_deviation, interquartile 등 breakpoint_threshold_type 설정 가능
    text_splitter = SemanticChunker(
        embeddings,
        breakpoint_threshold_type="percentile"
    )

    # 헤더로 분리된 각 섹션을 다시 의미론적으로 분할
    final_chunks = text_splitter.split_documents(header_splits)

    print(f"✂️ Chunking completed: Created {len(final_chunks)} chunks using SemanticChunker.")
    return final_chunks
