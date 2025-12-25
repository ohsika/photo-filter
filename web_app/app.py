import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import io
import zipfile

# --- 설정 및 디자인 ---
st.set_page_config(page_title="CAMPSMAP Film Lab", page_icon="📸")

st.title("📸 CAMPSMAP Film Lab")
st.markdown("""
스마트폰이나 디카로 찍은 사진을 **필름 감성**으로 현상해드립니다.
- **Grain**: 흑백 필름 입자감 추가
- **Vignette**: 가장자리 비네팅 효과
- **Auto Filter**: CAMPSMAP 전용 필터 자동 적용
""")

# --- 기능 함수들 (기존 로직 동일) ---

@st.cache_data
def load_filters():
    """Filters 폴더에서 필터 파일들을 미리 읽어옵니다."""
    filters = {}
    # 웹 서버(GitHub)상의 Filters 폴더 경로
    filter_dir = "Filters" 
    
    if not os.path.exists(filter_dir):
        return filters

    valid_extensions = ('.fit', '.flt')
    try:
        filter_files = [f for f in os.listdir(filter_dir) if f.lower().endswith(valid_extensions)]
        
        for fname in filter_files:
            full_path = os.path.join(filter_dir, fname)
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            if len(lines) < 7: continue

            def parse_line(line_str):
                return [int(x) for x in line_str.replace(',', ' ').split() if x.strip().isdigit()]

            r_lut = parse_line(lines[4])
            g_lut = parse_line(lines[5])
            b_lut = parse_line(lines[6])
            full_lut = r_lut + g_lut + b_lut

            if len(full_lut) < 768:
                full_lut += [full_lut[-1]] * (768 - len(full_lut))
            else:
                full_lut = full_lut[:768]
            
            filter_name = os.path.splitext(fname)[0]
            filters[filter_name] = full_lut
    except Exception:
        pass # 오류 무시
        
    return filters

def add_film_grain(image, intensity=12):
    if image.mode != 'RGB':
        image = image.convert('RGB')
    img_arr = np.array(image, dtype=np.float32)
    h, w, c = img_arr.shape
    noise = np.random.normal(0, intensity, (h, w))
    noise = np.repeat(noise[:, :, np.newaxis], 3, axis=2)
    grainy_img = img_arr + noise
    return Image.fromarray(np.clip(grainy_img, 0, 255).astype(np.uint8))

def add_vignette(image, intensity=0.4):
    if image.mode != 'RGB':
        image = image.convert('RGB')
    width, height = image.size
    x = np.linspace(-1, 1, width)
    y = np.linspace(-1, 1, height)
    X, Y = np.meshgrid(x, y)
    radius = np.sqrt(X**2 + Y**2)
    mask = 1 - np.clip(radius - 0.5, 0, 1) * intensity
    mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    img_arr = np.array(image, dtype=np.float32)
    vignetted = img_arr * mask
    return Image.fromarray(np.clip(vignetted, 0, 255).astype(np.uint8))

# --- 메인 화면 로직 ---

# 1. 필터 로드
loaded_filters = load_filters()
if not loaded_filters:
    st.warning("⚠️ 서버에 필터 파일이 없습니다. (Filters 폴더를 확인하세요)")

# 2. 파일 업로드 버튼
uploaded_files = st.file_uploader("사진을 여기에 드래그하거나 선택하세요 (여러 장 가능)", 
                                  type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🎞️ {len(uploaded_files)}장 현상 시작하기"):
        
        # 진행률 표시바
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # ZIP 파일 생성을 위한 메모리 버퍼
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for idx, uploaded_file in enumerate(uploaded_files):
                # 진행률 업데이트
                status_text.text(f"처리 중... {uploaded_file.name}")
                progress_bar.progress((idx + 1) / len(uploaded_files))
                
                # 이미지 처리
                image = Image.open(uploaded_file)
                image = ImageOps.exif_transpose(image)
                
                # 리사이징 (웹 속도를 위해 2000px 제한)
                image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
                
                # 베이스 효과
                base_img = image.filter(ImageFilter.GaussianBlur(0.3))
                vignetted_img = add_vignette(base_img, intensity=0.4)
                grain_img = add_film_grain(vignetted_img, intensity=12)
                
                file_name_no_ext = os.path.splitext(uploaded_file.name)[0]

                # 필터 적용 및 ZIP에 추가
                for filter_name, lut_data in loaded_filters.items():
                    try:
                        process_target = grain_img.convert('RGB')
                        final_img = process_target.point(lut_data)
                        
                        # 이미지를 메모리에 저장
                        img_byte_arr = io.BytesIO()
                        final_img.save(img_byte_arr, format='JPEG', quality=95, subsampling=0)
                        
                        # ZIP 파일 안에 넣기 (이름: 원본_필터명.jpg)
                        zip_file.writestr(f"{file_name_no_ext}_{filter_name}.jpg", img_byte_arr.getvalue())
                        
                    except Exception as e:
                        st.error(f"에러 발생: {e}")

        status_text.text("✅ 모든 작업 완료!")
        progress_bar.progress(100)
        
        # 3. 다운로드 버튼 생성
        st.success("현상이 완료되었습니다! 아래 버튼을 눌러 받으세요.")
        st.download_button(
            label="📦 완성된 사진 일괄 다운로드 (ZIP)",
            data=zip_buffer.getvalue(),
            file_name="CAMPSMAP_Results.zip",
            mime="application/zip"
        )
