import json
import os
import statistics

class ChunkEvaluator:
    def __init__(self, chunks):
        self.chunks = chunks
        self.stats = {}

    def analyze(self):
        """청크 통계 분석"""
        if not self.chunks:
            self.stats = {"count": 0, "avg_len": 0, "min_len": 0, "max_len": 0}
            return self.stats

        lengths = [len(chunk.page_content) for chunk in self.chunks]

        self.stats = {
            "count": len(lengths),
            "avg_len": round(statistics.mean(lengths), 2),
            "min_len": min(lengths),
            "max_len": max(lengths),
            "std_dev": round(statistics.stdev(lengths), 2) if len(lengths) > 1 else 0
        }
        return self.stats

    def save_report(self, output_dir="output"):
        """분석 리포트 및 청크 데이터 저장"""
        os.makedirs(output_dir, exist_ok=True)

        # 1. 텍스트 리포트
        report_path = os.path.join(output_dir, "chunk_report.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("=== Chunking Analysis Report ===\n")
            for k, v in self.stats.items():
                f.write(f"{k}: {v}\n")
            f.write("\n")

        # 2. 전체 청크 데이터 (JSON)
        json_path = os.path.join(output_dir, "chunks_debug.json")
        chunks_data = [
            {
                "id": i,
                "length": len(c.page_content),
                "metadata": c.metadata,
                "content": c.page_content
            }
            for i, c in enumerate(self.chunks)
        ]

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(chunks_data, f, ensure_ascii=False, indent=2)

        print(f"📊 Analysis complete. Report saved to: {output_dir}")
        print(f"   - Stats: {self.stats}")
