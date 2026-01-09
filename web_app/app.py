import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import io
import zipfile
import tempfile
import shutil
import gc

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Pro", page_icon="📸", layout="wide")

st.markdown("""
<style>
    div[data-testid="stImage"] { border-radius: 8px; overflow: hidden; }
    .stButton>button { border-radius: 8px; }
    div.stButton { margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 필터 설명 ---
FILTER_DESCRIPTIONS = {
    # 베이직
    "Classic": "표준 필름", "Vintage": "따뜻한 빈티지", "Mono": "부드러운 흑백",
    "Kino": "영화 색감", "Kodaclone": "코닥 스타일", "101Clone": "도시적 감성",
    "Art-Club": "몽환적 보라", "Boom-Boom": "강렬한 채도", "Bubblegum": "핑크 파스텔",
    "Cross-Pross": "청록색 틴트", "Eternia": "물 빠진 감성", "Grunge": "거친 락시크",
    "Midas": "황금빛 노을", "Narnia": "겨울 판타지", "Pastel": "순한 봄",
    "Pistachio": "싱그러운 녹색", "Temporum": "세피아 추억", "Uddh": "대지의 색",
    "X-Pro": "강한 대비", "Black_And_White": "강한 흑백", "Bleach": "묵직한 톤",
    # 트렌디 (느좋)
    "Sinsa_Mood": "성수/신사 매트한 톤",
    "Hannam_Chic": "세련된 화이트",
    "Fuji_Air": "후지필름 공기감",
    "Leica_Mono": "깊은 라이카 흑백",
    "Cinestill_Night": "푸른 밤 감성",
    "Portrait_Soft": "인물 피부톤 보정",
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

# --- [핵심] 자연스러운 이미지 처리 ---
def process_base_image(image_input, rotation=0, width=None):
    if isinstance(image_input, bytes):
        img = Image.open(io.BytesIO(image_input))
    else:
        img = image_input

    img = ImageOps.exif_transpose(img) 
    
    # 회전 적용
    if rotation != 0:
        img = img.rotate(rotation, expand=True)
    
    # 리사이징
    if width:
        w_percent = (width / float(img.size[0]))
        h_size = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((width, h_size), Image.Resampling.LANCZOS)
    
    # 1. 블러 (Blur): 0.3 -> 0.1 (거의 티 안 나게 렌즈 느낌만)
    base = img.filter(ImageFilter.GaussianBlur(0.1))
    
    w, h = base.size
    
    # 2. 비네팅 (Vignette): 0.4 -> 0.25 (아주 은은하게)
    x = np.linspace(-1, 1, w).astype(np.float32)
    y = np.linspace(-1, 1, h).astype(np.float32)
    X, Y = np.meshgrid(x, y)
    radius = np.sqrt(X**2 + Y**2)
    # 0.5부터 시작해서 부드럽게 어두워짐
    mask = 1 - np.clip(radius - 0.5, 0, 1) * 0.25 
    mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    
    arr = np.array(base.convert('RGB'), dtype=np.float32) * mask
    
    # 3. 그레인 (Grain): 12 -> 6 (고운 입자감)
    # 정규분포(Gaussian) 노이즈 사용
    noise = np.random.normal(0, 6, (h, w)).astype(np.float32)
    noise = np.repeat(noise[:, :, np.newaxis], 3, axis=2)
    
    final = np.clip(arr + noise, 0, 255).astype(np.uint8)
    
    del arr, noise, X, Y, mask
    return Image.fromarray(final)

def apply_lut(image, lut):
    return image.convert('RGB').point(lut)

# --- 세션 관리 ---
if 'temp_dir' not in st.session_state:
    st.session_state.temp_dir = tempfile.mkdtemp()
if 'saved_files_count' not in st.session_state:
    st.session_state.saved_files_count = 0
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'rotation_angle' not in st.session_state:
    st.session_state.rotation_angle = 0 # 회전 각도 유지용
if 'upload_key' not in st.session_state:
    st.session_state.upload_key = 0

# --- 메인 화면 ---
st.title("🎞️ CAMPSMAP Pro")
st.markdown("자연스러운 필름 그레인과 톤이 적용됩니다.")

loaded_filters = load_filters()
if not loaded_filters:
    st.error("⚠️ 필터 파일이 없습니다. GitHub를 확인하세요.")
    st.stop()

uploaded_files = st.file_uploader(
    "사진 업로드 (대량 가능)", 
    type=['jpg', 'jpeg', 'png'], 
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.upload_key}"
)

# 초기화
if not uploaded_files:
    st.session_state.current_index = 0
    st.session_state.saved_files_count = 0
    if os.path.exists(st.session_state.temp_dir):
        shutil.rmtree(st.session_state.temp_dir)
        st.session_state.temp_dir = tempfile.mkdtemp()

if uploaded_files:
    total_files = len(uploaded_files)
    
    # (A) 완료 화면
    if st.session_state.current_index >= total_files:
        st.success(f"🎉 {st.session_state.saved_files_count}장 현상 완료!")
        st.balloons()
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for root, dirs, files in os.walk(st.session_state.temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    zip_file.write(file_path, arcname=file)
        
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📦 전체 다운로드", data=zip_buffer.getvalue(), file_name="CAMPSMAP_Result.zip", mime="application/zip", type="primary", use_container_width=True)
        with c2:
            if st.button("🔄 새 작업 시작", use_container_width=True):
                st.session_state.upload_key += 1
                st.session_state.rotation_angle = 0
                st.rerun()

    # (B) 편집 화면
    else:
        gc.collect()
        current_file = uploaded_files[st.session_state.current_index]
        file_bytes = current_file.getvalue()
        
        st.progress((st.session_state.current_index) / total_files)
        
        # 정보 & 회전 버튼
        col_info, col_l, col_r = st.columns([4, 1, 1])
        with col_info:
            st.subheader(f"🖼️ [{st.session_state.current_index + 1}/{total_files}] {current_file.name}")
        with col_l:
            if st.button("↺ 왼쪽 회전"):
                st.session_state.rotation_angle = (st.session_state.rotation_angle + 90) % 360
                st.rerun()
        with col_r:
            if st.button("↻ 오른쪽 회전"):
                st.session_state.rotation_angle = (st.session_state.rotation_angle - 90) % 360
                st.rerun()

        # 미리보기
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
                submit = st.form_submit_button("✅ 저장 & 다음", type="primary", use_container_width=True)
            with b2:
                skip = st.form_submit_button("⏩ 패스", use_container_width=True)

        if submit:
            selected_filters = [k for k, v in selections.items() if v]
            if not selected_filters:
                st.warning("필터를 선택해주세요.")
            else:
                full_base = process_base_image(file_bytes, rotation=st.session_state.rotation_angle, width=2000)
                fname_no_ext = os.path.splitext(current_file.name)[0]
                
                with st.spinner("저장 중..."):
                    for f_name in selected_filters:
                        final = apply_lut(full_base, loaded_filters[f_name])
                        save_name = f"{fname_no_ext}_{f_name}.jpg"
                        save_path = os.path.join(st.session_state.temp_dir, save_name)
                        final.save(save_path, quality=95, subsampling=0)
                        del final
                        st.session_state.saved_files_count += 1
                
                del full_base
                st.session_state.current_index += 1
                st.rerun()

        if skip:
            st.session_state.current_index += 1
            st.rerun()
