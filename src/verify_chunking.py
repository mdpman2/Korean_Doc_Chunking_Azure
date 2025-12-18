import os
import sys
from dotenv import load_dotenv

# Add root to path
sys.path.append(os.getcwd())

# Load env before importing chunker which might use os.environ in global scope if any
load_dotenv()

from src.chunker import optimized_korean_chunking
from langchain_core.documents import Document

def test_chunking_real():
    print("🧪 Testing Real Semantic Chunking (requires valid .env)...")

    # Mock markdown text
    text = """
# 세금 제도 개편

2024년부터 세금 제도가 크게 개편됩니다.
소득세율이 조정되며, 공제 항목이 확대됩니다.

## 소득세
소득세 과세표준 구간이 상향 조정되었습니다.
이는 물가 상승률을 반영한 조치입니다.

## 법인세
법인세율은 인하되었습니다.
기업의 투자를 촉진하기 위함입니다.
"""

    try:
        chunks = optimized_korean_chunking(text)
        print("✅ Chunking Successful!")
        print(f"   Created {len(chunks)} chunks.")
        for i, chunk in enumerate(chunks):
            print(f"   Shape of Chunk #{i+1}: {len(chunk.page_content)} chars")
            print(f"   Snippet: {chunk.page_content[:50]}...")

    except Exception as e:
        print(f"❌ Chunking Failed: {e}")
        print("   -> Check your .env for AZURE_OPENAI_EMBEDDING_DEPLOYMENT, API_KEY, ENDPOINT, API_VERSION.")

if __name__ == "__main__":
    test_chunking_real()
