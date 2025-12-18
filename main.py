import os
from src.parser import HybridDocumentParser
from src.chunker import optimized_korean_chunking
from src.evaluator import ChunkEvaluator

def main():
    # 1. 설정
    input_pdf = "RAG_TEST_DATA/2014_08.pdf" # 테스트할 PDF 경로
    output_dir = "output"
    output_md = os.path.join(output_dir, "processed_doc.md")

    if not os.path.exists(input_pdf):
        print(f"⚠️ 파일이 없습니다: {input_pdf}")
        # return (for verification flow, we might want to proceed or warn, but existing logic returns)
        # However, if we want to test even without file, we might need a dummy mode, but sticking to file check is safer.
        return

    os.makedirs(output_dir, exist_ok=True)

    # 2. 파서 초기화 및 실행
    parser = HybridDocumentParser()
    markdown_content = parser.parse(input_pdf)

    # 3. 중간 결과 저장 (디버깅용)
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    print(f"💾 Parsed markdown saved to {output_md}")

    # 4. 청킹 실행
    chunks = optimized_korean_chunking(markdown_content)

    # 5. 결과 확인 및 평가
    evaluator = ChunkEvaluator(chunks)
    evaluator.analyze()
    evaluator.save_report(output_dir)

    print("\n--- [Preview Chunks] ---")
    for i, chunk in enumerate(chunks[:10]):
        print(f"\n🧩 Chunk #{i+1}")
        print(f"Metadata: {chunk.metadata}")
        print(f"Content: {chunk.page_content[:250]}...") # 앞부분만 출력
        print("-" * 50)

if __name__ == "__main__":
    main()
