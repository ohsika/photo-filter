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
    .stButton>button { border-radius: 8px; }
    /* 버튼 스타일 통일 */
    div.stButton { margin-top: 5px; margin-bottom: 5px; }
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
}

# --- 필터 로딩 (정밀 진단 모드) ---
@st.cache_data
def load_filters_with_diagnosis():
    filters = {}
    errors = [] 
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [os.path.join(current_dir, "Filters"), "Filters"]
    
    found_path = None
    for p in possible_paths:
        if os.path.exists(p):
            found_path = p
            break
            
    if not found_path:
        return filters, ["❌ 'Filters' 폴더 자체를 못 찾았습니다."]

    target_files = [f for f in os.listdir(found_path) if f.lower().endswith(('.fit', '.flt'))]
    
    for fname in target_files:
        full_path = os.path.join(found_path, fname)
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            if len(lines) < 3: 
                errors.append(f"⚠️ {fname}: 내용이 너무 짧습니다.")
                continue

            lut = []
            for line in lines:
                parts = [x for x in line.replace(',', ' ').split() if x.strip().replace('-','').isdigit()]
                if len(parts) > 10:
                    lut.extend([int(x) for x in parts])
            
            if len(lut) == 0:
                errors.append(f"⚠️ {fname}: 숫자 데이터 없음.")
                continue

            if len(lut) == 256: lut = lut * 3
            if len(lut) < 768: lut += [lut[-1]] * (768 - len(lut))
            else: lut = lut[:768]
            
            f_name_clean = os.path.splitext(fname)[0]
            filters[f_name_clean] = lut

        except Exception as e:
            errors.append(f"❌ {fname}: 오류 ({str(e)})")
            
    return filters, errors

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

# ------------------------------------------------
# [진단 결과 표시]
loaded_filters, error_logs = load_filters_with_diagnosis()
with st.expander(f"📊 시스템 리포트 (성공: {len(loaded_filters)}개)", expanded=False):
    if error_logs:
        for err in error_logs: st.write(err)
    else:
        st.success("모든 필터 정상 로드됨")
# ------------------------------------------------

uploaded_files = st.file_uploader("사진 업로드", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True, key=f"uploader_{st.session_state.upload_key}")

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
        st.success(f"🎉 {st.session_state.saved_files_count}장 완료!")
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
    
    # (B) 편집 화면
    else:
        gc.collect()
        current_file = uploaded_files[st.session_state.current_index]
        st.progress((st.session_state.current_index)/total_files)
        
        # 정보 & 회전
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
        
        # --- [FORM 시작] ---
        with st.form(key=f"form_{st.session_state.current_index}"):
            
            # ----------------------------------------------------
            # [상단 버튼 구역] (사용자 요청 추가)
            # ----------------------------------------------------
            t_prev, t_save, t_skip = st.columns([1, 2, 1])
            with t_prev:
                # 첫 번째 사진이면 '이전' 버튼 비활성화
                disable_prev = (st.session_state.current_index == 0)
                top_go_prev = st.form_submit_button("⬅️ 이전", disabled=disable_prev, use_container_width=True)
            with t_save:
                top_submit = st.form_submit_button("✅ 저장 & 다음", type="primary", use_container_width=True)
            with t_skip:
                top_skip = st.form_submit_button("⏩ 패스", use_container_width=True)
            
            st.divider()

            # 필터 선택 그리드
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
                st.error("로드된 필터가 없습니다.")
                selections = {}

            st.divider()
            
            # ----------------------------------------------------
            # [하단 버튼 구역] (기존 유지)
            # ----------------------------------------------------
            b_prev, b_save, b_skip = st.columns([1, 2, 1])
            with b_prev:
                # 상단과 동일한 로직의 하단 버튼
                bottom_go_prev = st.form_submit_button("⬅️ 이전 (Prev)", disabled=disable_prev, use_container_width=True)
            with b_save:
                bottom_submit = st.form_submit_button("✅ 저장 & 다음 (Save)", type="primary", use_container_width=True)
            with b_skip:
                bottom_skip = st.form_submit_button("⏩ 패스 (Skip)", use_container_width=True)


        # --- 로직 처리 (상단/하단 버튼 모두 작동하게 OR 조건 사용) ---

        # 1. [저장 & 다음] 버튼
        if top_submit or bottom_submit:
            selected_filters = [k for k, v in selections.items() if v]
            if not selected_filters:
                st.warning("선택된 필터가 없습니다.")
            else:
                full_base = process_base_image(current_file.getvalue(), rotation=st.session_state.rotation_angle, width=2000)
                fname_no_ext = os.path.splitext(current_file.name)[0]
                with st.spinner("저장 중..."):
                    for f_name in selected_filters:
                        final = apply_lut(full_base, loaded_filters[f_name])
                        final.save(os.path.join(st.session_state.temp_dir, f"{fname_no_ext}_{f_name}.jpg"), quality=95, subsampling=0)
                        st.session_state.saved_files_count += 1
                st.session_state.current_index += 1
                st.rerun()

        # 2. [스킵] 버튼
        if top_skip or bottom_skip:
            st.session_state.current_index += 1
            st.rerun()

        # 3. [이전] 버튼 (Undo 기능)
        if top_go_prev or bottom_go_prev:
            prev_index = st.session_state.current_index - 1
            if prev_index >= 0:
                # 이전 파일 정보 찾기
                prev_file_name = uploaded_files[prev_index].name
                prev_name_no_ext = os.path.splitext(prev_file_name)[0]
                
                # 임시 폴더에서 이전 파일의 저장본들 삭제 (Undo)
                deleted_count = 0
                for f in os.listdir(st.session_state.temp_dir):
                    if f.startswith(f"{prev_name_no_ext}_"):
                        try:
                            os.remove(os.path.join(st.session_state.temp_dir, f))
                            deleted_count += 1
                        except: pass
                
                st.session_state.saved_files_count -= deleted_count
                st.session_state.current_index = prev_index
                st.toast(f"이전 사진으로 돌아갑니다. (취소된 저장: {deleted_count}장)")
                st.rerun()
