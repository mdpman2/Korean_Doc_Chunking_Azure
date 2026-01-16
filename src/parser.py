import os
import base64
import re
from io import BytesIO
from PIL import Image
from pdf2image import convert_from_path
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

class HybridDocumentParser:
    def __init__(self):
        self.di_client = DocumentIntelligenceClient(
            endpoint=os.getenv("AZURE_DI_ENDPOINT"),
            credential=AzureKeyCredential(os.getenv("AZURE_DI_KEY"))
        )
        self.aoai_client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        self.gpt_model = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    def _encode_image_base64(self, pil_image):
        buffered = BytesIO()
        pil_image.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def _describe_image(self, pil_image, image_idx, context_hint=""):
        """GPT-4o를 사용하여 이미지의 핵심 인사이트를 텍스트로 추출"""
        print(f"   🤖 GPT-4o Analyzing Figure #{image_idx}...")
        base64_img = self._encode_image_base64(pil_image)

        system_prompt = """당신은 한글 문서 분석 전문가입니다. 주어진 이미지를 보고 RAG(검색 증강 생성) 시스템이 이해할 수 있도록 상세하게 설명하세요.

[이미지 유형별 분석 가이드]
1. **소프트웨어 스크린샷/UI 화면**:
   - 어떤 프로그램/메뉴인지 명시
   - 클릭해야 할 버튼, 메뉴 경로, 설정값을 정확히 기술
   - 단계별 조작 방법이 보이면 순서대로 설명

2. **표(Table)**:
   - 행/열 구조를 파악하고 데이터를 텍스트로 변환
   - 번호(No.), 항목명, 설명 등 컬럼 정보 유지
   - 셀 병합이 있으면 해당 관계 설명

3. **다이어그램/순서도**:
   - 화살표 방향, 흐름 순서 설명
   - 각 단계/노드의 내용 기술

4. **차트/그래프**:
   - 데이터 수치, 추세, 핵심 메시지 서술
   - 범례, 축 레이블 정보 포함

[출력 규칙]
- 한국어로 명확하게 서술
- 검색에 유용한 키워드를 포함
- 단순 시각 묘사보다 '무엇을 할 수 있는지', '어떤 정보인지' 중심으로 설명"""

        user_prompt = "이 이미지의 내용을 상세히 설명해줘."
        if context_hint:
            user_prompt += f"\n\n참고 문맥: {context_hint}"

        try:
            response = self.aoai_client.chat.completions.create(
                model=self.gpt_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                    ]}
                ],
                temperature=0.0,
                max_tokens=1500
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"   ❌ Error analyzing image: {e}")
            return "[이미지 분석 실패]"

    def _extract_tables_enhanced(self, result: AnalyzeResult) -> dict:
        """Document Intelligence 결과에서 표 정보를 상세히 추출"""
        tables_info = {}

        if not result.tables:
            return tables_info

        print(f"📊 Found {len(result.tables)} tables. Processing...")

        for table_idx, table in enumerate(result.tables):
            # 표의 행/열 구조 파악
            rows = {}
            for cell in table.cells:
                row_idx = cell.row_index
                col_idx = cell.column_index
                content = cell.content.strip() if cell.content else ""

                if row_idx not in rows:
                    rows[row_idx] = {}

                # 셀 병합 처리
                row_span = cell.row_span if hasattr(cell, 'row_span') and cell.row_span else 1
                col_span = cell.column_span if hasattr(cell, 'column_span') and cell.column_span else 1

                rows[row_idx][col_idx] = {
                    'content': content,
                    'row_span': row_span,
                    'col_span': col_span,
                    'kind': cell.kind if hasattr(cell, 'kind') else 'content'
                }

            # Markdown 표 생성
            table_md = self._rows_to_markdown_table(rows, table.column_count)

            # 표 위치 정보 (offset 기준)
            if table.spans:
                offset = table.spans[0].offset
                tables_info[offset] = {
                    'index': table_idx + 1,
                    'markdown': table_md,
                    'row_count': table.row_count,
                    'col_count': table.column_count
                }

        return tables_info

    def _rows_to_markdown_table(self, rows: dict, col_count: int) -> str:
        """행 데이터를 Markdown 표로 변환"""
        if not rows:
            return ""

        md_lines = []
        sorted_rows = sorted(rows.keys())

        for row_idx in sorted_rows:
            row_data = rows[row_idx]
            cells = []
            for col_idx in range(col_count):
                cell_info = row_data.get(col_idx, {'content': ''})
                cells.append(cell_info['content'])
            md_lines.append("| " + " | ".join(cells) + " |")

            # 첫 행 뒤에 구분선 추가 (헤더로 간주)
            if row_idx == sorted_rows[0]:
                md_lines.append("|" + "|".join(["---"] * col_count) + "|")

        return "\n".join(md_lines)

    def _enhance_numbered_lists(self, markdown_text: str) -> str:
        """번호 목록 형식 보존 및 개선 (06, 07 같은 형식)"""
        # "06 제목" 형식을 "### 06. 제목" 형식으로 변환
        pattern = r'^(\d{2})\s+(.+)$'
        lines = markdown_text.split('\n')
        enhanced_lines = []

        for line in lines:
            match = re.match(pattern, line.strip())
            if match:
                num, title = match.groups()
                enhanced_lines.append(f"\n### {num}. {title}\n")
            else:
                enhanced_lines.append(line)

        return '\n'.join(enhanced_lines)

    def _extract_context_around_figure(self, markdown_text: str, offset: int, window: int = 200) -> str:
        """이미지 주변의 텍스트 문맥 추출"""
        start = max(0, offset - window)
        end = min(len(markdown_text), offset + window)
        context = markdown_text[start:end]
        # 문장 단위로 정리
        context = re.sub(r'\s+', ' ', context).strip()
        return context[:300] if len(context) > 300 else context

    def parse(self, file_path):
        """
        파일 형식(PDF, PPTX, DOCX)에 따라 하이브리드 파싱 수행
        - PDF: Azure DI + Visual RAG (이미지 크롭 & 설명)
        - PPTX/DOCX: Azure DI (텍스트/표 파싱) - 이미지 설명은 스킵 (Pure Python 한계)

        개선 사항:
        - 표(Table) 구조 상세 파싱
        - 번호 목록 형식 보존
        - 한글 문서 UI 스크린샷 인식 강화
        """
        file_ext = os.path.splitext(file_path)[1].lower()
        print(f"🚀 Parsing started: {file_path} ({file_ext})")

        # 1. Image 변환 (PDF인 경우만)
        page_images = None
        if file_ext == '.pdf':
            try:
                # poppler 필요
                page_images = convert_from_path(file_path, dpi=200)
            except Exception as e:
                print(f"   ⚠️ PDF Image conversion failed (Visual RAG will be skipped): {e}")

        # 2. Azure Document Intelligence 실행
        # PDF, PPTX, DOCX, HTML 등 다양한 포맷 지원
        with open(file_path, "rb") as f:
            poller = self.di_client.begin_analyze_document(
                model_id="prebuilt-layout",
                body=f,
                content_type="application/octet-stream",
                output_content_format="markdown"  # Markdown 출력 요청
                # locale="ko-KR", # Document Intelligence 에서는 locale이 모델 옵션에 따라 다를 수 있음. prebuilt-layout에선 보통 자동 감지.
            )
        result = poller.result()

        full_markdown = result.content
        descriptions = []

        # 2.5. 표 정보 상세 추출 및 강화
        tables_info = self._extract_tables_enhanced(result)
        print(f"   📋 Enhanced {len(tables_info)} tables with detailed structure")

        # 3. Figure(이미지/차트) 감지 및 GPT-4o 처리 (PDF이고 이미지가 변환된 경우에만)
        if result.figures and page_images:
            print(f"📊 Found {len(result.figures)} figures. Starting vision analysis...")

            for idx, figure in enumerate(result.figures):
                if not figure.bounding_regions: continue

                region = figure.bounding_regions[0]
                page_num = region.page_number - 1

                # 페이지 범위 체크
                if page_num >= len(page_images):
                    continue

                page_img = page_images[page_num]
                # di_page = result.pages[page_num] # New SDK might handle pages differently, checking structure.
                # In new SDK, result.pages is a list of DocumentPage
                di_page = result.pages[page_num] # Assuming page index matches

                # 좌표 스케일링
                polygon = region.polygon
                x_coords = [p.x for p in polygon]
                y_coords = [p.y for p in polygon]

                # 0으로 나누기 방지
                if di_page.width == 0 or di_page.height == 0:
                    continue

                scale_x = page_img.width / di_page.width
                scale_y = page_img.height / di_page.height

                left = min(x_coords) * scale_x
                top = min(y_coords) * scale_y
                right = max(x_coords) * scale_x
                bottom = max(y_coords) * scale_y

                # 이미지 크롭
                try:
                    cropped_img = page_img.crop((left, top, right, bottom))
                    # 너무 작은 이미지는 스킵 (선택사항)
                    if cropped_img.width < 50 or cropped_img.height < 50:
                        continue

                    # 주변 문맥 추출
                    offset = figure.spans[0].offset if figure.spans else len(full_markdown)
                    context_hint = self._extract_context_around_figure(full_markdown, offset)

                    # GPT-4o 분석 (문맥 힌트 포함)
                    desc_text = self._describe_image(cropped_img, idx + 1, context_hint)

                    insertion_block = f"\n\n> **[이미지/차트 설명 {idx+1}]**\n> {desc_text}\n\n"

                    descriptions.append((offset, insertion_block))

                except Exception as e:
                    print(f"   ⚠️ Error cropping/analyzing figure {idx+1}: {e}")

        elif result.figures and not page_images:
             print(f"ℹ️ Figures detected but Visual RAG skipped for non-PDF format: {file_ext}")

        # 4. 설명 텍스트 병합
        descriptions.sort(key=lambda x: x[0], reverse=True)

        for offset, text in descriptions:
            if offset <= len(full_markdown):
                full_markdown = full_markdown[:offset] + text + full_markdown[offset:]
            else:
                full_markdown += text

        # 5. 번호 목록 형식 개선
        full_markdown = self._enhance_numbered_lists(full_markdown)

        # 6. 최종 정리
        # 연속된 빈 줄 정리
        full_markdown = re.sub(r'\n{4,}', '\n\n\n', full_markdown)

        print("✅ Parsing completed.")
        return full_markdown
