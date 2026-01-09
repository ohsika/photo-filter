import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import io
import zipfile

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Film Lab", page_icon="📸", layout="wide")

# --- [사용자 설정] 필터 설명 적는 곳 ---
# 가지고 계신 필터 파일 이름(확장자 제외)에 맞춰서 설명을 적어주세요.
# 여기에 없는 파일은 기본 설명("Custom Filter")이 나옵니다.
FILTER_INFO = {
    "Classic": "🎞️ 가장 표준적인 필름 룩, 부드러운 대비",
    "Vintage": "🍂 빛 바랜 느낌, 따뜻한 색감",
    "Mono": "🕶️ 흑백 느와르 감성",
    "Kino": "🎬 영화 같은 시네마틱 톤",
    "Kodaclone": "📷 코닥 필름 스타일의 진한 색감",
    "101Clone": "🏙️ 차분하고 모던한 도시 감성",
    # 필요한 만큼 계속 추가하시면 됩니다.
    # "파일이름": "설명",
}

st.title("📸 CAMPSMAP Film Lab")
st.markdown("""
**나만의 필름 현상소에 오신 것을 환영합니다.**  
디지털 사진에 아날로그의 온도와 질감을 입혀보세요.
""")

# --- 핵심 기능: 필터 로딩 ---
@st.cache_data
def load_filters():
    filters = {}
    current_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [
        os.path.join(current_dir, "Filters"),
        os.path.join(current_dir, "web_app", "Filters"),
        "Filters"
    ]
    valid_extensions = ('.fit', '.flt')

    for filter_dir in possible_paths:
        if not os.path.exists(filter_dir): continue
        try:
            files = [f for f in os.listdir(filter_dir) if f.lower().endswith(valid_extensions)]
            for fname in files:
                filter_name = os.path.splitext(fname)[0]
                if filter_name in filters: continue 

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
                
                filters[filter_name] = full_lut
        except: pass
    return filters

# --- 이미지 처리 함수들 ---
def add_film_grain(image, intensity=12):
    if image.mode != 'RGB': image = image.convert('RGB')
    img_arr = np.array(image, dtype=np.float32)
    h, w, c = img_arr.shape
    noise = np.random.normal(0, intensity, (h, w))
    noise = np.repeat(noise[:, :, np.newaxis], 3, axis=2)
    grainy_img = img_arr + noise
    return Image.fromarray(np.clip(grainy_img, 0, 255).astype(np.uint8))

def add_vignette(image, intensity=0.4):
    if image.mode != 'RGB': image = image.convert('RGB')
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

# 1. 사이드바: 필터 로드 및 선택
with st.sidebar:
    st.header("🎨 필터 선택")
    loaded_filters = load_filters()
    
    if not loaded_filters:
        st.error("⚠️ 로드된 필터가 없습니다.")
    else:
        st.success(f"✅ {len(loaded_filters)}개의 필터 로드됨")
        
        # 필터 이름 리스트
        all_filter_names = list(loaded_filters.keys())
        
        # 필터 선택 박스 (설명 포함)
        selected_filter_names = st.multiselect(
            "적용할 필터를 선택하세요:",
            options=all_filter_names,
            default=all_filter_names, # 기본값: 전체 선택
            format_func=lambda x: f"{x} - {FILTER_INFO.get(x, '')}" # 이름 옆에 설명 표시
        )
        
        st.info("💡 Tip: 여러 개를 선택하면 한 번에 여러 버전으로 현상해줍니다.")

# 2. 메인 화면: 업로드 및 결과
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. 사진 업로드")
    uploaded_files = st.file_uploader("변환할 사진을 올려주세요 (JPG, PNG)", 
                                      type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

with col2:
    st.subheader("2. 현상 결과")
    
    # 실행 조건: 파일이 있고 + 필터도 선택되었을 때
    if uploaded_files and selected_filter_names:
        if st.button(f"🎞️ {len(uploaded_files)}장 사진 현상 시작 (Start)"):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            zip_buffer = io.BytesIO()
            
            total_operations = len(uploaded_files)
            
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                for idx, uploaded_file in enumerate(uploaded_files):
                    status_text.text(f"Processing [{idx+1}/{total_operations}]: {uploaded_file.name}")
                    progress_bar.progress((idx + 1) / total_operations)
                    
                    try:
                        image = Image.open(uploaded_file)
                        image = ImageOps.exif_transpose(image)
                        image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
                        
                        # 공통 베이스 효과
                        base_img = image.filter(ImageFilter.GaussianBlur(0.3))
                        vignetted_img = add_vignette(base_img, intensity=0.4)
                        grain_img = add_film_grain(vignetted_img, intensity=12)
                        
                        file_name_no_ext = os.path.splitext(uploaded_file.name)[0]

                        # [핵심 변경] 선택된 필터만 반복
                        for filter_name in selected_filter_names:
                            try:
                                lut_data = loaded_filters[filter_name]
                                process_target = grain_img.convert('RGB')
                                final_img = process_target.point(lut_data)
                                
                                img_byte_arr = io.BytesIO()
                                final_img.save(img_byte_arr, format='JPEG', quality=95, subsampling=0)
                                
                                zip_file.writestr(f"{file_name_no_ext}_{filter_name}.jpg", img_byte_arr.getvalue())
                            except: continue
                                
                    except Exception as e:
                        st.error(f"오류: {uploaded_file.name} - {e}")

            status_text.text("✅ 현상 완료!")
            progress_bar.progress(100)
            
            st.success("작업이 완료되었습니다. 아래 버튼으로 다운로드하세요.")
            st.download_button(
                label="📦 결과물 일괄 다운로드 (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="CAMPSMAP_Results.zip",
                mime="application/zip",
                use_container_width=True
            )
    
    elif uploaded_files and not selected_filter_names:
        st.warning("👈 왼쪽 사이드바에서 적용할 필터를 최소 1개 이상 선택해주세요.")
