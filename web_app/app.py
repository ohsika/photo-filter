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
st.set_page_config(page_title="CAMPSMAP Debugger", page_icon="🐞", layout="wide")

st.markdown("""
<style>
    div[data-testid="stImage"] { border-radius: 8px; overflow: hidden; }
    .stButton>button { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------
# [긴급 진단] 파일 시스템 눈으로 확인하기
# -----------------------------------------------------------
with st.expander("🚨 필터가 안 보일 때 여기를 눌러보세요 (시스템 진단)", expanded=True):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    st.write(f"📍 현재 앱이 실행되는 위치: `{current_dir}`")
    
    # 1. 현재 폴더에 무엇이 있는지 확인
    try:
        root_files = os.listdir(current_dir)
        st.write(f"📂 현재 폴더 파일 목록 ({len(root_files)}개):", root_files)
        
        if "Filters" in root_files:
            st.success("✅ 'Filters' 폴더가 발견되었습니다!")
            filter_path = os.path.join(current_dir, "Filters")
            inner_files = os.listdir(filter_path)
            st.write(f"📂 Filters 폴더 안의 내용물 ({len(inner_files)}개):", inner_files)
            
            fit_files = [f for f in inner_files if f.lower().endswith(('.fit', '.flt'))]
            if fit_files:
                st.success(f"🎉 필터 파일 {len(fit_files)}개를 찾았습니다! (정상)")
            else:
                st.error("❌ Filters 폴더는 있는데, 그 안에 .fit / .flt 파일이 없습니다.")
        else:
            st.error("❌ 현재 위치에 'Filters' 폴더가 없습니다. 대소문자(Filters vs filters)를 확인하거나 파일이 업로드되었는지 확인하세요.")
            
    except Exception as e:
        st.error(f"진단 중 오류 발생: {e}")
# -----------------------------------------------------------

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
}

# --- 필터 파일 생성기 (다운로드용) ---
def generate_filter_zip():
    zip_buffer = io.BytesIO()
    def curve_s(x, intensity=0.04): return 255 / (1 + math.exp(-intensity * (x - 128)))
    x_val = list(range(256))
    
    recipes = {
        "Classic": ([curve_s(x, 0.04) for x in x_val], [curve_s(x, 0.04) for x in x_val], [curve_s(x, 0.04) for x in x_val]),
        "Vintage": ([curve_s(x)*1.1+10 for x in x_val], [curve_s(x)*1.0+5 for x in x_val], [curve_s(x)*0.9 for x in x_val]),
        "Mono": ([curve_s(x, 0.05) for x in x_val], [curve_s(x, 0.05) for x in x_val], [curve_s(x, 0.05) for x in x_val]),
        # ... (필요 시 더 추가 가능, 용량상 줄임)
    }
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for name, (r, g, b) in recipes.items():
            r = [min(255, max(0, int(v))) for v in r]
            g = [min(255, max(0, int(v))) for v in g]
            b = [min(255, max(0, int(v))) for v in b]
            content = f"Filter Data\nCAMPSMAP\nRGB\n{', '.join(map(str, r))}\n{', '.join(map(str, g))}\n{', '.join(map(str, b))}\n"
            zip_file.writestr(f"{name}.flt", content)
    return zip_buffer.getvalue()

# --- 필터 로딩 (강력한 탐색) ---
@st.cache_data
def load_filters():
    filters = {}
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 탐색 경로를 더 다양하게 추가
    possible_paths = [
        os.path.join(current_dir, "Filters"),
        os.path.join(current_dir, "filters"), # 소문자 대응
        "Filters",
        "filters"
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

# --- 세션 ---
if 'temp_dir' not in st.session_state: st.session_state.temp_dir = tempfile.mkdtemp()
if 'saved_files_count' not in st.session_state: st.session_state.saved_files_count = 0
if 'current_index' not in st.session_state: st.session_state.current_index = 0
if 'rotation_angle' not in st.session_state: st.session_state.rotation_angle = 0 
if 'upload_key' not in st.session_state: st.session_state.upload_key = 0

# --- 메인 ---
st.title("🎞️ CAMPSMAP Pro")

with st.sidebar:
    st.header("🛠️ 관리자 도구")
    st.download_button("📥 필터 생성 및 다운로드 (ZIP)", data=generate_filter_zip(), file_name="CAMPSMAP_Filters.zip", mime="application/zip")

loaded_filters = load_filters()
if not loaded_filters:
    st.warning("⚠️ 필터가 로드되지 않았습니다! 상단 '시스템 진단'을 확인하세요.")

uploaded_files = st.file_uploader("사진 업로드", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True, key=f"uploader_{st.session_state.upload_key}")

if not uploaded_files:
    st.session_state.current_index = 0
    st.session_state.saved_files_count = 0
    if os.path.exists(st.session_state.temp_dir):
        shutil.rmtree(st.session_state.temp_dir)
        st.session_state.temp_dir = tempfile.mkdtemp()

if uploaded_files:
    total_files = len(uploaded_files)
    if st.session_state.current_index >= total_files:
        st.success(f"🎉 {st.session_state.saved_files_count}장 완료!")
        st.balloons()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for root, dirs, files in os.walk(st.session_state.temp_dir):
                for file in files:
                    zip_file.write(os.path.join(root, file), arcname=file)
        c1, c2 = st.columns(2)
        with c1: st.download_button("📦 전체 다운로드", data=zip_buffer.getvalue(), file_name="Result.zip", mime="application/zip", type="primary", use_container_width=True)
        with c2: 
            if st.button("🔄 새 작업", use_container_width=True):
                st.session_state.upload_key += 1
                st.session_state.rotation_angle = 0
                st.rerun()
    else:
        gc.collect()
        current_file = uploaded_files[st.session_state.current_index]
        st.progress((st.session_state.current_index)/total_files)
        col_info, col_l, col_r = st.columns([4, 1, 1])
        with col_info: st.subheader(f"🖼️ [{st.session_state.current_index + 1}/{total_files}] {current_file.name}")
        with col_l: 
            if st.button("↺ 왼쪽"): 
                st.session_state.rotation_angle = (st.session_state.rotation_angle + 90) % 360
                st.rerun()
        with col_r: 
            if st.button("↻ 오른쪽"): 
                st.session_state.rotation_angle = (st.session_state.rotation_angle - 90) % 360
                st.rerun()

        preview_img = process_base_image(current_file.getvalue(), rotation=st.session_state.rotation_angle, width=300)
        
        with st.form(key=f"form_{st.session_state.current_index}"):
            if loaded_filters:
                filter_names = sorted(list(loaded_filters.keys()))
                cols = st.columns(4)
                selections = {}
                for idx, f_name in enumerate(filter_names):
                    with cols[idx % 4]:
                        st.image(apply_lut(preview_img, loaded_filters[f_name]), use_container_width=True)
                        desc = FILTER_DESCRIPTIONS.get(f_name, "")
                        label = f"**{f_name}**\n:gray[{desc}]" if desc else f"**{f_name}**"
                        selections[f_name] = st.checkbox(label, key=f"chk_{st.session_state.current_index}_{f_name}")
            else:
                st.error("필터가 없습니다.")
                selections = {}

            st.divider()
            b1, b2 = st.columns([2, 1])
            with b1: submit = st.form_submit_button("✅ 저장 & 다음", type="primary", use_container_width=True)
            with b2: skip = st.form_submit_button("⏩ 패스", use_container_width=True)

        if submit:
            selected_filters = [k for k, v in selections.items() if v]
            if not selected_filters: st.warning("선택된 필터가 없습니다.")
            else:
                full_base = process_base_image(current_file.getvalue(), rotation=st.session_state.rotation_angle, width=2000)
                fname_no_ext = os.path.splitext(current_file.name)[0]
                with st.spinner("저장 중..."):
                    for f_name in selected_filters:
                        final = apply_lut(full_base, loaded_filters[f_name])
                        save_name = f"{fname_no_ext}_{f_name}.jpg"
                        final.save(os.path.join(st.session_state.temp_dir, save_name), quality=95, subsampling=0)
                        st.session_state.saved_files_count += 1
                st.session_state.current_index += 1
                st.rerun()

        if skip:
            st.session_state.current_index += 1
            st.rerun()
