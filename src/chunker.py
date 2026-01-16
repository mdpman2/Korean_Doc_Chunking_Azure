import re
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import AzureOpenAIEmbeddings
from langchain.schema import Document
import os

def preserve_table_chunks(markdown_text: str) -> list:
    """표(Table)를 별도 청크로 분리하여 보존"""
    # Markdown 표 패턴 감지
    table_pattern = r'(\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n?)+)'

    tables = []
    for match in re.finditer(table_pattern, markdown_text):
        tables.append({
            'content': match.group(0),
            'start': match.start(),
            'end': match.end()
        })

    return tables

def split_by_numbered_sections(markdown_text: str) -> list:
    """번호 섹션(06, 07 등)별로 분할"""
    # "### 06." 또는 "## 06" 형식의 섹션 감지
    pattern = r'(###?\s*\d{2}\.?\s+[^\n]+)'

    sections = []
    last_end = 0

    for match in re.finditer(pattern, markdown_text):
        if match.start() > last_end:
            # 이전 섹션의 내용
            content = markdown_text[last_end:match.start()].strip()
            if content:
                sections.append(content)
        last_end = match.start()

    # 마지막 섹션
    if last_end < len(markdown_text):
        content = markdown_text[last_end:].strip()
        if content:
            sections.append(content)

    return sections if sections else [markdown_text]

def optimized_korean_chunking(markdown_text: str, preserve_tables: bool = True, preserve_numbered: bool = True):
    """
    1단계: 표(Table)와 번호 섹션 보존
    2단계: Markdown Header 기준으로 의미 단위 분리
    3단계: Azure OpenAI Embedding을 이용한 Semantic Chunking

    개선 사항:
    - 표(Table) 구조 보존 (하나의 청크로 유지)
    - 번호 목록(06, 07 등) 섹션 분리
    - 이미지 설명 블록 보존
    """

    # 0. 이미지/차트 설명 블록 추출 및 임시 보존
    image_blocks = []
    image_pattern = r'(> \*\*\[이미지/차트 설명 \d+\]\*\*\n(?:> .+\n?)+)'
    for match in re.finditer(image_pattern, markdown_text):
        image_blocks.append({
            'content': match.group(0),
            'placeholder': f'__IMAGE_BLOCK_{len(image_blocks)}__'
        })

    # 이미지 블록을 플레이스홀더로 치환
    processed_text = markdown_text
    for block in image_blocks:
        processed_text = processed_text.replace(block['content'], block['placeholder'])

    # 1. 표 추출 및 별도 처리
    table_chunks = []
    if preserve_tables:
        tables = preserve_table_chunks(processed_text)
        for i, table in enumerate(tables):
            # 표를 플레이스홀더로 치환
            placeholder = f'__TABLE_{i}__'
            processed_text = processed_text.replace(table['content'], placeholder)

            # 표 주변 컨텍스트 찾기 (표 앞의 제목/설명)
            table_start = table['start']
            context_start = max(0, table_start - 200)
            context = markdown_text[context_start:table_start].strip()
            # 마지막 줄만 추출 (보통 표 제목)
            context_lines = context.split('\n')
            table_title = context_lines[-1] if context_lines else ""

            table_chunks.append(Document(
                page_content=f"{table_title}\n\n{table['content']}",
                metadata={
                    'type': 'table',
                    'table_index': i + 1,
                    'title': table_title[:50] if table_title else f"Table {i+1}"
                }
            ))
        print(f"   📊 Preserved {len(table_chunks)} tables as separate chunks")

    # 2. 구조적 분할 (Header 기준)
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
        ("####", "Header 4"),
    ]

    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)

    try:
        header_splits = markdown_splitter.split_text(processed_text)
    except Exception as e:
        print(f"   ⚠️ Header splitting failed: {e}")
        # 폴백: 단순 텍스트 분할
        header_splits = [Document(page_content=processed_text, metadata={})]

    # 3. 의미론적 분할 (Semantic Chunking)
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
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=85  # 더 큰 청크 유지
    )

    # 헤더로 분리된 각 섹션을 다시 의미론적으로 분할
    try:
        semantic_chunks = text_splitter.split_documents(header_splits)
    except Exception as e:
        print(f"   ⚠️ Semantic chunking failed: {e}")
        # 폴백: RecursiveCharacterTextSplitter 사용
        fallback_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
        )
        semantic_chunks = fallback_splitter.split_documents(header_splits)

    # 4. 이미지 블록 복원 및 별도 청크 생성
    image_doc_chunks = []
    for block in image_blocks:
        # 해당 이미지 블록이 포함된 청크 찾기
        for chunk in semantic_chunks:
            if block['placeholder'] in chunk.page_content:
                # 플레이스홀더를 실제 이미지 설명으로 복원
                chunk.page_content = chunk.page_content.replace(
                    block['placeholder'],
                    block['content']
                )

        # 이미지 설명을 별도 청크로도 생성 (검색 용이성)
        image_doc_chunks.append(Document(
            page_content=block['content'],
            metadata={
                'type': 'image_description',
                'original_block': True
            }
        ))

    # 5. 모든 청크 병합
    final_chunks = semantic_chunks + table_chunks + image_doc_chunks

    # 6. 청크 메타데이터 정리 및 번호 할당
    for i, chunk in enumerate(final_chunks):
        chunk.metadata['chunk_id'] = i + 1
        chunk.metadata['char_count'] = len(chunk.page_content)

        # 청크 유형 분류
        if chunk.metadata.get('type') not in ['table', 'image_description']:
            if '> **[이미지/차트 설명' in chunk.page_content:
                chunk.metadata['contains_image_desc'] = True
            if re.search(r'###?\s*\d{2}\.', chunk.page_content):
                chunk.metadata['contains_numbered_section'] = True

    print(f"✂️ Chunking completed: Created {len(final_chunks)} chunks")
    print(f"   - Semantic chunks: {len(semantic_chunks)}")
    print(f"   - Table chunks: {len(table_chunks)}")
    print(f"   - Image description chunks: {len(image_doc_chunks)}")

    return final_chunks
