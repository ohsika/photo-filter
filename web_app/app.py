import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import io
import zipfile
import tempfile
import shutil
import gc  # 가비지 컬렉션 (메모리 청소부)

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Pro", page_icon="📸", layout="wide")

# --- 스타일링 ---
st.markdown("""
<style>
    div[data-testid="stImage"] { border-radius: 10px; overflow: hidden; }
    .stButton>button { border-radius: 8px; }
    div.stButton { margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 필터 데이터 ---
FILTER_DESCRIPTIONS = {
    "Classic": "표준 필름", "Vintage": "따뜻한 빈티지", "Mono": "부드러운 흑백",
    "Kino": "영화 색감", "Kodaclone": "코닥 스타일", "101Clone": "도시적 감성",
    "Art-Club": "몽환적 보라", "Boom-Boom": "강렬한 채도", "Bubblegum": "핑크 파스텔",
    "Cross-Pross": "청록색 틴트", "Eternia": "물 빠진 감성", "Grunge": "거친 락시크",
    "Midas": "황금빛 노을", "Narnia": "겨울 판타지", "Pastel": "순한 봄",
    "Pistachio": "싱그러운 녹색", "Temporum": "세피아 추억", "Uddh": "대지의 색",
    "X-Pro": "강한 대비", "Black_And_White": "강한 흑백", "Bleach": "묵직한 톤"
}

# --- 필터 로딩 ---
@st.cache_data
def load_filters():
    filters = {}
    current_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [
        os.path.join(current_dir, "Filters"),
        os.path.join(current_dir, "web_app", "Filters"),
        "Filters"
    ]
    
    for filter_dir in possible_paths:
        if not os.path.exists(filter_dir): continue
        try:
            files = [f for f in os.listdir(filter_dir) if f.lower().endswith(('.fit', '.flt'))]
            for fname in files:
                f_name = os.path.splitext(fname)[0]
                if f_name in filters: continue
                with open(os.path.join(filter_dir, fname), 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                if len(lines) < 7: continue
                lut = []
                for i in range(4, 7):
                    line_data = [int(x) for x in lines[i].replace(',', ' ').split() if x.strip().isdigit()]
                    lut.extend(line_data)
                if len(lut) < 768: lut += [lut[-1]] * (768 - len(lut))
                else: lut = lut[:768]
                filters[f_name] = lut
        except: pass
    return filters

# --- 이미지 처리 ---
def process_base_image(image_input, rotation=0, width=None):
    """이미지 객체 생성 및 기본 효과 적용"""
    # 메모리 효율을 위해BytesIO 대신 바로 Image 객체 처리 시도
    if isinstance(image_input, bytes):
        img = Image.open(io.BytesIO(image_input))
    else:
        img = image_input

    img = ImageOps.exif_transpose(img) 
    
    if rotation != 0:
        img = img.rotate(-rotation, expand=True)
    
    if width:
        w_percent = (width / float(img.size[0]))
        h_size = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((width, h_size), Image.Resampling.LANCZOS)
    
    base = img.filter(ImageFilter.GaussianBlur(0.3))
    
    # Numpy 연산 최적화
    w, h = base.size
    # 비네팅 마스크 (가볍게 계산)
    x = np.linspace(-1, 1, w).astype(np.float32)
    y = np.linspace(-1, 1, h).astype(np.float32)
    X, Y = np.meshgrid(x, y)
    radius = np.sqrt(X**2 + Y**2)
    mask = 1 - np.clip(radius - 0.5, 0, 1) * 0.4
    mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    
    arr = np.array(base.convert('RGB'), dtype=np.float32) * mask
    
    # 그레인 (메모리 절약을 위해 int8 변환 고려했으나 화질 위해 float 유지 후 클립)
    noise = np.random.normal(0, 12, (h, w)).astype(np.float32)
    noise = np.repeat(noise[:, :, np.newaxis], 3, axis=2)
    
    final = np.clip(arr + noise, 0, 255).astype(np.uint8)
    
    # 사용한 무거운 객체들 즉시 삭제
    del arr, noise, X, Y, mask
    
    return Image.fromarray(final)

def apply_lut(image, lut):
    return image.convert('RGB').point(lut)

# --- 세션 관리 (임시 폴더 사용) ---
if 'temp_dir' not in st.session_state:
    # 임시 폴더 생성 (디스크에 저장하기 위함)
    st.session_state.temp_dir = tempfile.mkdtemp()
    
if 'saved_files_count' not in st.session_state:
    st.session_state.saved_files_count = 0

if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'rotation_angle' not in st.session_state:
    st.session_state.rotation_angle = 0
if 'upload_key' not in st.session_state:
    st.session_state.upload_key = 0

# --- 메인 화면 ---
st.title("🎞️ CAMPSMAP Pro")
st.markdown("대용량 작업에 최적화된 버전입니다. **메모리 부족 방지를 위해 자동 최적화**가 적용됩니다.")

loaded_filters = load_filters()
if not loaded_filters:
    st.error("⚠️ 필터 파일이 없습니다.")
    st.stop()

uploaded_files = st.file_uploader(
    "사진을 업로드하세요 (100장 이상 가능)", 
    type=['jpg', 'jpeg', 'png'], 
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.upload_key}"
)

# 파일 리스트 변경 시 초기화
if not uploaded_files:
    st.session_state.current_index = 0
    st.session_state.saved_files_count = 0
    st.session_state.rotation_angle = 0
    # 임시 폴더 비우기 (새 작업 시작 시)
    if os.path.exists(st.session_state.temp_dir):
        shutil.rmtree(st.session_state.temp_dir)
        st.session_state.temp_dir = tempfile.mkdtemp()

if uploaded_files:
    total_files = len(uploaded_files)
    
    # (A) 완료 화면
    if st.session_state.current_index >= total_files:
        st.success(f"🎉 총 {st.session_state.saved_files_count}장의 사진이 처리되었습니다!")
        st.balloons()
        
        # ZIP 생성 (디스크에서 읽어서 생성)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            # 임시 폴더의 파일들을 순회
            for root, dirs, files in os.walk(st.session_state.temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    zip_file.write(file_path, arcname=file)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📦 전체 결과물 다운로드", 
                data=zip_buffer.getvalue(), 
                file_name="CAMPSMAP_Batch.zip", 
                mime="application/zip", 
                type="primary",
                use_container_width=True
            )
        with col2:
            if st.button("🔄 새 작업 시작", use_container_width=True):
                st.session_state.upload_key += 1
                st.rerun()

    # (B) 편집 화면
    else:
        # 가비지 컬렉션 강제 수행 (이전 루프의 메모리 해제)
        gc.collect()
        
        current_file = uploaded_files[st.session_state.current_index]
        file_bytes = current_file.getvalue()
        
        st.progress((st.session_state.current_index) / total_files)
        
        c1, c2 = st.columns([3, 1])
        with c1:
            st.subheader(f"🖼️ [{st.session_state.current_index + 1}/{total_files}] {current_file.name}")
        with c2:
            if st.button("🔄 90° 회전"):
                st.session_state.rotation_angle = (st.session_state.rotation_angle + 90) % 360
                st.rerun()

        # 미리보기 (작은 사이즈)
        preview_img = process_base_image(file_bytes, rotation=st.session_state.rotation_angle, width=300)
        
        with st.form(key=f"form_{st.session_state.current_index}"):
            filter_names = sorted(list(loaded_filters.keys()))
            cols = st.columns(4)
            selections = {}
            
            for idx, f_name in enumerate(filter_names):
                with cols[idx % 4]:
                    thumb = apply_lut(preview_img, loaded_filters[f_name])
                    st.image(thumb, use_container_width=True)
                    desc = FILTER_DESCRIPTIONS.get(f_name, "")
                    label = f"**{f_name}**"
                    if desc: label += f"\n:gray[{desc}]"
                    selections[f_name] = st.checkbox(label, key=f"chk_{st.session_state.current_index}_{f_name}")
            
            st.divider()
            b1, b2 = st.columns([2, 1])
            with b1:
                submit = st.form_submit_button("✅ 저장 & 다음 (Save)", type="primary", use_container_width=True)
            with b2:
                skip = st.form_submit_button("⏩ 패스 (Skip)", use_container_width=True)

        if submit:
            selected_filters = [k for k, v in selections.items() if v]
            
            if not selected_filters:
                st.warning("선택된 필터가 없습니다.")
            else:
                # 고화질 변환 (2000px)
                full_base = process_base_image(file_bytes, rotation=st.session_state.rotation_angle, width=2000)
                fname_no_ext = os.path.splitext(current_file.name)[0]
                
                with st.spinner("디스크에 저장 중..."):
                    for f_name in selected_filters:
                        final = apply_lut(full_base, loaded_filters[f_name])
                        
                        # [핵심] 메모리가 아닌 디스크(임시폴더)에 바로 저장
                        save_name = f"{fname_no_ext}_{f_name}.jpg"
                        save_path = os.path.join(st.session_state.temp_dir, save_name)
                        
                        final.save(save_path, quality=95, subsampling=0)
                        
                        # 메모리 해제
                        del final
                        st.session_state.saved_files_count += 1
                
                # 원본 이미지 메모리 해제
                del full_base
                
                st.session_state.rotation_angle = 0
                st.session_state.current_index += 1
                st.rerun()

        if skip:
            st.session_state.rotation_angle = 0
            st.session_state.current_index += 1
            st.rerun()
