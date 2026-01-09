import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import io
import zipfile
import tempfile
import shutil
import gc
import math

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Pro", page_icon="📸", layout="wide")

st.markdown("""
<style>
    div[data-testid="stImage"] { border-radius: 8px; overflow: hidden; }
    .stButton>button { border-radius: 8px; width: 100%; }
    .status-container {
        padding: 10px; 
        background-color: #f0f2f6; 
        border-radius: 10px; 
        margin-bottom: 20px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- 필터 설명 ---
FILTER_DESCRIPTIONS = {
    "Classic": "표준 필름", "Vintage": "따뜻한 빈티지", "Mono": "부드러운 흑백",
    "Kino": "영화 색감", "Kodaclone": "코닥 스타일", "101Clone": "도시적 감성",
    "Art-Club": "몽환적 보라", "Boom-Boom": "강렬한 채도", "Bubblegum": "핑크 파스텔",
    "Cross-Pross": "청록색 틴트", "Eternia": "물 빠진 감성", "Grunge": "거친 락시크",
    "Midas": "황금빛 노을", "Narnia": "겨울 판타지", "Pastel": "순한 봄",
    "Pistachio": "싱그러운 녹색", "Temporum": "세피아 추억", "Uddh": "대지의 색",
    "X-Pro": "강한 대비", "Black_And_White": "강한 흑백", "Bleach": "묵직한 톤",
    "Sinsa_Mood": "성수/신사 매트한 톤", "Hannam_Chic": "세련된 화이트",
    "Fuji_Air": "후지필름 공기감", "Leica_Mono": "깊은 라이카 흑백",
    "Cinestill_Night": "푸른 밤 감성", "Portrait_Soft": "인물 피부톤 보정",
    "Film_Noir": "거친 느와르 영화"
}

# --- 필터 순서 ---
PREFERRED_ORDER = [
    "Sinsa_Mood", "Hannam_Chic", "Fuji_Air", "Leica_Mono", "Cinestill_Night", "Portrait_Soft",
    "Classic", "Vintage", "Mono", "Kodaclone", "Kino", "101Clone",
    "Eternia", "Narnia", "Black_And_White", "Film_Noir"
]

# --- 필터 로딩 ---
@st.cache_data
def load_filters():
    filters = {}
    current_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [os.path.join(current_dir, "Filters"), "Filters"]
    
    for filter_dir in possible_paths:
        if not os.path.exists(filter_dir): continue
        try:
            files = [f for f in os.listdir(filter_dir) if f.lower().endswith(('.fit', '.flt'))]
            for fname in files:
                f_name = os.path.splitext(fname)[0]
                if f_name in filters: continue
                with open(os.path.join(filter_dir, fname), 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                if len(lines) < 3: continue
                lut = []
                for line in lines:
                    parts = [int(x) for x in line.replace(',', ' ').split() if x.strip().replace('-','').isdigit()]
                    if len(parts) > 10: lut.extend(parts)
                if not lut: continue
                if len(lut) == 256: lut = lut * 3
                if len(lut) < 768: lut += [lut[-1]] * (768 - len(lut))
                else: lut = lut[:768]
                filters[f_name] = lut
        except: pass
    return filters

# --- 필터 다운로드 생성기 ---
def generate_filter_zip():
    zip_buffer = io.BytesIO()
    def s(x, i=0.04): return 255 / (1 + math.exp(-i * (x - 128)))
    x_v = list(range(256))
    recipes = {
        "Classic": ([s(x) for x in x_v], [s(x) for x in x_v], [s(x) for x in x_v]),
        "Vintage": ([s(x)*1.1+10 for x in x_v], [s(x)*1.0+5 for x in x_v], [s(x)*0.9 for x in x_v]),
        "Sinsa_Mood": ([s(x,0.03)*1.05 for x in x_v], [s(x,0.03)*1.02 for x in x_v], [s(x,0.03)*0.9+10 for x in x_v]),
        "Hannam_Chic": ([s(x,0.05)*0.95 for x in x_v], [s(x,0.05) for x in x_v], [s(x,0.05)*1.1 for x in x_v]),
        "Fuji_Air": ([x*0.95 for x in x_v], [s(x,0.04)*1.05 for x in x_v], [x*1.1+5 for x in x_v]),
        "Leica_Mono": ([s(x,0.06) for x in x_v], [s(x,0.06) for x in x_v], [s(x,0.06) for x in x_v]),
    }
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for name, (r, g, b) in recipes.items():
            r = [min(255, max(0, int(v))) for v in r]
            g = [min(255, max(0, int(v))) for v in g]
            b = [min(255, max(0, int(v))) for v in b]
            content = f"RGB\n{', '.join(map(str, r))}\n{', '.join(map(str, g))}\n{', '.join(map(str, b))}\n"
            zip_file.writestr(f"{name}.flt", content)
    return zip_buffer.getvalue()

# --- 이미지 처리 ---
def process_base_image(image_input, rotation=0, width=None):
    if isinstance(image_input, bytes): img = Image.open(io.BytesIO(image_input))
    else: img = image_input
    img = ImageOps.exif_transpose(img) 
    if rotation != 0: img = img.rotate(rotation, expand=True)
    if width:
        w_p = (width / float(img.size[0]))
        h_s = int((float(img.size[1]) * float(w_p)))
        img = img.resize((width, h_s), Image.Resampling.LANCZOS)
    
    base = img.filter(ImageFilter.GaussianBlur(0.1))
    w, h = base.size
    x, y = np.meshgrid(np.linspace(-1, 1, w).astype(np.float32), np.linspace(-1, 1, h).astype(np.float32))
    mask = 1 - np.clip(np.sqrt(x**2 + y**2)-0.5, 0, 1)*0.25 
    mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    arr = np.array(base.convert('RGB'), dtype=np.float32) * mask
    noise = np.random.normal(0, 6, (h, w)).astype(np.float32)
    noise = np.repeat(noise[:, :, np.newaxis], 3, axis=2)
    final = np.clip(arr + noise, 0, 255).astype(np.uint8)
    del arr, noise, mask
    return Image.fromarray(final)

def apply_lut(image, lut): return image.convert('RGB').point(lut)

# --- 세션 관리 ---
WORK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_workspace")
if not os.path.exists(WORK_DIR): os.makedirs(WORK_DIR)

if 'saved_files_count' not in st.session_state: st.session_state.saved_files_count = 0
if 'current_index' not in st.session_state: st.session_state.current_index = 0
if 'rotation_angle' not in st.session_state: st.session_state.rotation_angle = 0 
if 'upload_key' not in st.session_state: st.session_state.upload_key = 0

# --- 메인 UI 시작 ---
st.title("🎞️ CAMPSMAP Pro")

with st.sidebar:
    st.header("🛠️ 관리자")
    st.download_button("📥 필터 다운로드", data=generate_filter_zip(), file_name="CAMPSMAP_Filters.zip", mime="application/zip")

loaded_filters = load_filters()
if not loaded_filters:
    st.warning("⚠️ 필터가 없습니다. 왼쪽에서 다운로드 후 업로드하세요.")

uploaded_files = st.file_uploader("사진 업로드", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True, key=f"uploader_{st.session_state.upload_key}")

# 초기화
if uploaded_files:
    if 'last_upload_count' not in st.session_state or st.session_state.last_upload_count != len(uploaded_files):
        st.session_state.last_upload_count = len(uploaded_files)
        st.session_state.current_index = 0
        st.session_state.saved_files_count = 0
        if os.path.exists(WORK_DIR):
            shutil.rmtree(WORK_DIR)
            os.makedirs(WORK_DIR)

    total_files = len(uploaded_files)
    
    # [수정] 진행 바를 가장 먼저 표시 (무조건 보이게)
    current_idx = st.session_state.current_index
    progress_val = min(current_idx / total_files, 1.0)
    st.progress(progress_val)
    
    # 상태 표시 박스
    st.markdown(f"""
        <div class="status-container">
            💾 저장된 사진: {st.session_state.saved_files_count}장 &nbsp; | &nbsp; 🖼️ 진행 순서: {current_idx + 1} / {total_files}
        </div>
    """, unsafe_allow_html=True)

    # (A) 완료 화면
    if current_idx >= total_files:
        st.success(f"🎉 총 {st.session_state.saved_files_count}장 작업 완료!")
        st.balloons()
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for root, dirs, files in os.walk(WORK_DIR):
                for file in files:
                    zip_file.write(os.path.join(root, file), arcname=file)
        
        c1, c2 = st.columns(2)
        with c1: st.download_button("📦 전체 다운로드", data=zip_buffer.getvalue(), file_name="Result.zip", mime="application/zip", type="primary", use_container_width=True)
        with c2: 
            if st.button("🔄 새 작업 시작", use_container_width=True):
                st.session_state.upload_key += 1
                st.session_state.rotation_angle = 0
                st.rerun()
    
    # (B) 편집 화면
    else:
        gc.collect()
        current_file = uploaded_files[current_idx]
        
        # 회전 컨트롤
        c_l, c_title, c_r = st.columns([1, 4, 1])
        with c_l: 
            if st.button("↺ 왼쪽 회전"): 
                st.session_state.rotation_angle = (st.session_state.rotation_angle + 90) % 360
                st.rerun()
        with c_title:
            st.markdown(f"<h3 style='text-align: center;'>{current_file.name}</h3>", unsafe_allow_html=True)
        with c_r: 
            if st.button("↻ 오른쪽 회전"): 
                st.session_state.rotation_angle = (st.session_state.rotation_angle - 90) % 360
                st.rerun()

        # 미리보기 생성
        preview_img = process_base_image(current_file.getvalue(), rotation=st.session_state.rotation_angle, width=300)
        
        with st.form(key=f"form_{current_idx}"):
            
            # [수정] 상단 버튼 배치 (1:1:1 비율)
            t1, t2, t3 = st.columns(3)
            with t1:
                # 이전 버튼 (첫장이면 비활성)
                d_prev = (current_idx == 0)
                top_prev = st.form_submit_button("⬅️ 이전", disabled=d_prev)
            with t2:
                top_save = st.form_submit_button("✅ 선택 저장", type="primary")
            with t3:
                top_skip = st.form_submit_button("⏩ 건너뛰기 (Pass)")

            st.divider()

            # 필터 그리드
            all_keys = list(loaded_filters.keys())
            sorted_keys = [f for f in PREFERRED_ORDER if f in all_keys]
            remaining = sorted([f for f in all_keys if f not in PREFERRED_ORDER])
            final_list = sorted_keys + remaining

            cols = st.columns(4)
            selections = {}
            for idx, f_name in enumerate(final_list):
                with cols[idx % 4]:
                    st.image(apply_lut(preview_img, loaded_filters[f_name]), use_container_width=True)
                    desc = FILTER_DESCRIPTIONS.get(f_name, "")
                    label = f"**{f_name}**\n:gray[{desc}]" if desc else f"**{f_name}**"
                    selections[f_name] = st.checkbox(label, key=f"chk_{current_idx}_{f_name}")

            st.divider()
            
            # 하단 버튼
            b1, b2, b3 = st.columns(3)
            with b1: bot_prev = st.form_submit_button("⬅️ 이전", disabled=d_prev)
            with b2: bot_save = st.form_submit_button("✅ 선택 저장", type="primary")
            with b3: bot_skip = st.form_submit_button("⏩ 건너뛰기 (Pass)")

        # --- 로직 ---
        # 1. 저장
        if top_save or bot_save:
            selected = [k for k, v in selections.items() if v]
            if not selected:
                st.warning("선택된 필터가 없습니다.")
            else:
                full_base = process_base_image(current_file.getvalue(), rotation=st.session_state.rotation_angle, width=2000)
                fname_no_ext = os.path.splitext(current_file.name)[0]
                if not os.path.exists(WORK_DIR): os.makedirs(WORK_DIR)
                with st.spinner("저장 중..."):
                    for f_name in selected:
                        final = apply_lut(full_base, loaded_filters[f_name])
                        final.save(os.path.join(WORK_DIR, f"{fname_no_ext}_{f_name}.jpg"), quality=95, subsampling=0)
                        st.session_state.saved_files_count += 1
                st.session_state.current_index += 1
                st.rerun()

        # 2. 패스
        if top_skip or bot_skip:
            st.session_state.current_index += 1
            st.rerun()

        # 3. 이전
        if top_prev or bot_prev:
            prev_idx = current_idx - 1
            if prev_idx >= 0:
                prev_file_name = uploaded_files[prev_idx].name
                prev_no_ext = os.path.splitext(prev_file_name)[0]
                deleted = 0
                if os.path.exists(WORK_DIR):
                    for f in os.listdir(WORK_DIR):
                        if f.startswith(f"{prev_no_ext}_"):
                            try:
                                os.remove(os.path.join(WORK_DIR, f))
                                deleted += 1
                            except: pass
                st.session_state.saved_files_count -= deleted
                if st.session_state.saved_files_count < 0: st.session_state.saved_files_count = 0
                st.session_state.current_index = prev_idx
                st.toast(f"이전으로 돌아감 (취소된 사진: {deleted}장)")
                st.rerun()
