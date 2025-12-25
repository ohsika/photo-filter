import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import io
import zipfile

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Film Lab", page_icon="📸")

st.title("📸 CAMPSMAP Film Lab")
st.markdown("""
**필름 감성 현상소**에 오신 것을 환영합니다.
사진을 업로드하면 필름 그레인, 비네팅, 그리고 전용 색감 필터를 입혀드립니다.
""")

# --- 핵심 기능: 강력한 필터 로딩 ---
@st.cache_data
def load_filters():
    """
    여러 경로를 탐색하여 .fit 또는 .flt 파일을 찾습니다.
    (GitHub 폴더 구조가 꼬여도 찾을 수 있게 설계됨)
    """
    filters = {}
    
    # 현재 app.py가 실행되는 위치 확인
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 탐색할 후보 경로들 (순서대로 찾음)
    possible_paths = [
        os.path.join(current_dir, "Filters"),           # 1. 같은 폴더
        os.path.join(current_dir, "web_app", "Filters"),# 2. 하위 web_app 폴더
        "Filters"                                       # 3. 상대 경로
    ]
    
    valid_extensions = ('.fit', '.flt')
    checked_paths = [] # 디버깅용: 어디어디 찾아봤는지 기록

    for filter_dir in possible_paths:
        checked_paths.append(filter_dir)
        
        if not os.path.exists(filter_dir):
            continue

        try:
            files = [f for f in os.listdir(filter_dir) if f.lower().endswith(valid_extensions)]
            
            for fname in files:
                filter_name = os.path.splitext(fname)[0]
                if filter_name in filters: continue # 중복 로드 방지

                full_path = os.path.join(filter_dir, fname)
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                
                # 데이터 파싱 (최소 7줄 체크)
                if len(lines) < 7: continue

                def parse_line(line_str):
                    return [int(x) for x in line_str.replace(',', ' ').split() if x.strip().isdigit()]

                r_lut = parse_line(lines[4])
                g_lut = parse_line(lines[5])
                b_lut = parse_line(lines[6])
                full_lut = r_lut + g_lut + b_lut

                # 768개 데이터 맞추기
                if len(full_lut) < 768:
                    full_lut += [full_lut[-1]] * (768 - len(full_lut))
                else:
                    full_lut = full_lut[:768]
                
                filters[filter_name] = full_lut
                
        except Exception:
            pass # 개별 파일 오류는 무시하고 계속 진행
            
    return filters, checked_paths

# --- 이미지 처리 함수들 ---
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

# --- 메인 실행 로직 ---

# 1. 필터 로드 시도
loaded_filters, checked_paths = load_filters()

# 2. 로드 결과 확인 및 경고 메시지
if not loaded_filters:
    st.error("⚠️ 필터 파일을 찾지 못했습니다!")
    st.write("다음 경로들을 찾아보았으나 비어있거나 없습니다:")
    for p in checked_paths:
        st.code(p)
    st.info("GitHub에 'Filters' 폴더가 있고, 그 안에 .fit/.flt 파일이 들어있는지 확인해주세요.")
else:
    st.success(f"✅ {len(loaded_filters)}개의 필터가 준비되었습니다.")

# 3. 파일 업로드
uploaded_files = st.file_uploader("변환할 사진을 선택하세요 (여러 장 가능)", 
                                  type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

if uploaded_files and loaded_filters:
    if st.button(f"🎞️ {len(uploaded_files)}장 현상 시작 (Start)"):
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"Processing... {uploaded_file.name}")
                progress_bar.progress((idx + 1) / len(uploaded_files))
                
                # 이미지 열기
                try:
                    image = Image.open(uploaded_file)
                    image = ImageOps.exif_transpose(image) # 회전 보정
                    
                    # 웹 속도 최적화 (Max 2000px)
                    image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
                    
                    # 베이스 효과 (그레인, 비네팅)
                    base_img = image.filter(ImageFilter.GaussianBlur(0.3))
                    vignetted_img = add_vignette(base_img, intensity=0.4)
                    grain_img = add_film_grain(vignetted_img, intensity=12)
                    
                    file_name_no_ext = os.path.splitext(uploaded_file.name)[0]

                    # 각 필터 적용하여 저장
                    for filter_name, lut_data in loaded_filters.items():
                        try:
                            process_target = grain_img.convert('RGB')
                            final_img = process_target.point(lut_data)
                            
                            # 메모리에 저장
                            img_byte_arr = io.BytesIO()
                            final_img.save(img_byte_arr, format='JPEG', quality=95, subsampling=0)
                            
                            # ZIP에 추가
                            zip_file.writestr(f"{file_name_no_ext}_{filter_name}.jpg", img_byte_arr.getvalue())
                        except:
                            continue
                            
                except Exception as e:
                    st.error(f"오류 발생 ({uploaded_file.name}): {e}")

        status_text.text("✅ 작업 완료!")
        progress_bar.progress(100)
        
        st.success("현상이 완료되었습니다! 버튼을 눌러 다운로드하세요.")
        st.download_button(
            label="📦 결과물 다운로드 (ZIP)",
            data=zip_buffer.getvalue(),
            file_name="CAMPSMAP_Results.zip",
            mime="application/zip"
        )
