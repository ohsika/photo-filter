import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import io
import zipfile

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Film Lab", page_icon="📸", layout="wide")

# ==========================================
# [사용자 설정] 필터 설명 & 이름 정리
# ==========================================
# 1. 여기에 파일명(확장자 제외)과 설명을 적으세요.
FILTER_DESCRIPTIONS = {
    "Classic": "표준 필름 룩",
    "Vintage": "따뜻한 빛바램",
    "Mono": "흑백 느와르",
    "Kino": "영화 같은 색감",
    "Kodaclone": "코닥 스타일",
    "101Clone": "도시적/차분함",
    # 여기에 없는 파일은 "Custom Filter"라고 뜸
}

# 2. 이름이 너무 길 때 자동으로 줄여주는 함수
def format_filter_name(name):
    # (1) 불필요한 단어 제거 (예시: -Camper-Snapper 제거)
    name = name.replace("-Camper-Snapper", "")
    name = name.replace("_", " ") # 언더바를 공백으로
    
    # (2) 그래도 15글자 넘으면 잘라내기
    if len(name) > 15:
        return name[:13] + ".."
    return name
# ==========================================

st.title("📸 CAMPSMAP Film Lab")
st.markdown("디지털 사진에 **아날로그 감성**을 입혀보세요.")

# --- 필터 로딩 로직 ---
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
                
                # 데이터 파싱 및 보정
                r = parse_line(lines[4])
                g = parse_line(lines[5])
                b = parse_line(lines[6])
                full_lut = r + g + b

                if len(full_lut) < 768: full_lut += [full_lut[-1]] * (768 - len(full_lut))
                else: full_lut = full_lut[:768]
                
                filters[filter_name] = full_lut
        except: pass
    return filters

# --- 이미지 처리 함수 ---
def process_image_effect(image, intensity_grain=12, intensity_vignette=0.4):
    if image.mode != 'RGB': image = image.convert('RGB')
    
    # 1. 비네팅
    width, height = image.size
    x = np.linspace(-1, 1, width)
    y = np.linspace(-1, 1, height)
    X, Y = np.meshgrid(x, y)
    radius = np.sqrt(X**2 + Y**2)
    mask = 1 - np.clip(radius - 0.5, 0, 1) * intensity_vignette
    mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    img_arr = np.array(image, dtype=np.float32) * mask
    
    # 2. 그레인
    h, w, c = img_arr.shape
    noise = np.random.normal(0, intensity_grain, (h, w))
    noise = np.repeat(noise[:, :, np.newaxis], 3, axis=2)
    grainy_img = img_arr + noise
    
    return Image.fromarray(np.clip(grainy_img, 0, 255).astype(np.uint8))

# --- UI 및 실행 로직 ---
loaded_filters = load_filters()

# [사이드바] 필터 체크리스트 UI
with st.sidebar:
    st.header("🎨 필터 선택")
    
    if not loaded_filters:
        st.error("⚠️ 필터 파일이 없습니다.")
        selected_filter_names = []
    else:
        st.write(f"총 {len(loaded_filters)}개의 필터가 있습니다.")
        
        # 전체 선택/해제 기능
        col_all, col_none = st.columns(2)
        all_checked = col_all.button("전체 선택")
        none_checked = col_none.button("전체 해제")
        
        # 세션 상태로 체크박스 값 관리
        if "filter_checks" not in st.session_state or all_checked:
            st.session_state.filter_checks = {name: True for name in loaded_filters.keys()}
        if none_checked:
            st.session_state.filter_checks = {name: False for name in loaded_filters.keys()}

        # 체크리스트 출력 (Expander 안에 넣어서 깔끔하게)
        selected_filter_names = []
        with st.expander("필터 목록 열기/닫기", expanded=True):
            for f_name in loaded_filters.keys():
                # 이름 예쁘게 다듬기
                display_name = format_filter_name(f_name)
                # 설명 가져오기
                desc = FILTER_DESCRIPTIONS.get(f_name, "Custom Filter")
                
                # 체크박스 라벨 디자인: [굵은 이름] - [설명]
                label_md = f"**{display_name}**  \n:gray[{desc}]"
                
                # 체크박스 생성
                is_checked = st.checkbox(
                    label_md, 
                    value=st.session_state.filter_checks.get(f_name, True),
                    key=f"chk_{f_name}"
                )
                
                if is_checked:
                    selected_filter_names.append(f_name)

# [메인 화면]
col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("1. 사진 업로드")
    uploaded_files = st.file_uploader("", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    
    # 선택된 필터 정보 표시
    if selected_filter_names:
        st.info(f"👉 **{len(selected_filter_names)}개**의 필터가 적용됩니다.")
    else:
        st.warning("👈 왼쪽에서 필터를 하나 이상 선택해주세요.")

with col2:
    st.subheader("2. 결과 다운로드")
    
    if uploaded_files and selected_filter_names:
        if st.button("🎞️ 현상 시작 (Start Processing)", type="primary", use_container_width=True):
            
            progress_bar = st.progress(0)
            status_area = st.empty()
            zip_buffer = io.BytesIO()
            
            total_ops = len(uploaded_files)
            
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                for idx, uploaded_file in enumerate(uploaded_files):
                    status_area.text(f"Processing... {uploaded_file.name}")
                    progress_bar.progress((idx + 1) / total_ops)
                    
                    try:
                        # 이미지 열기 & 전처리
                        img = Image.open(uploaded_file)
                        img = ImageOps.exif_transpose(img)
                        img.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
                        
                        # 베이스 효과 (그레인/비네팅)
                        base_img = img.filter(ImageFilter.GaussianBlur(0.3))
                        ready_img = process_image_effect(base_img)
                        
                        fname_no_ext = os.path.splitext(uploaded_file.name)[0]

                        # 선택된 필터들 적용
                        for f_name in selected_filter_names:
                            try:
                                lut = loaded_filters[f_name]
                                final_img = ready_img.convert('RGB').point(lut)
                                
                                # 메모리 저장 -> ZIP
                                img_bytes = io.BytesIO()
                                final_img.save(img_bytes, format='JPEG', quality=95, subsampling=0)
                                zip_file.writestr(f"{fname_no_ext}_{f_name}.jpg", img_bytes.getvalue())
                            except: continue
                            
                    except Exception as e:
                        st.error(f"Error: {uploaded_file.name} - {e}")

            status_area.success("✅ 모든 작업이 완료되었습니다!")
            progress_bar.progress(100)
            
            st.download_button(
                label="📦 ZIP 파일 다운로드",
                data=zip_buffer.getvalue(),
                file_name="CAMPSMAP_Results.zip",
                mime="application/zip",
                use_container_width=True
            )
