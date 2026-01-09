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
st.set_page_config(page_title="CAMPSMAP Debugger", page_icon="🕵️", layout="wide")

st.markdown("""
<style>
    div[data-testid="stImage"] { border-radius: 8px; overflow: hidden; }
    .stButton>button { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# --- 필터 로딩 (정밀 진단 모드) ---
@st.cache_data
def load_filters_with_diagnosis():
    filters = {}
    errors = [] # 에러 로그 저장소
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [
        os.path.join(current_dir, "Filters"),
        "Filters"
    ]
    
    found_path = None
    for p in possible_paths:
        if os.path.exists(p):
            found_path = p
            break
            
    if not found_path:
        return filters, ["❌ 'Filters' 폴더 자체를 못 찾았습니다."]

    # 파일 목록 가져오기
    all_files = os.listdir(found_path)
    target_files = [f for f in all_files if f.lower().endswith(('.fit', '.flt'))]
    
    for fname in target_files:
        full_path = os.path.join(found_path, fname)
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            # [진단 1] 파일 내용이 너무 짧음
            if len(lines) < 3: 
                errors.append(f"⚠️ {fname}: 내용이 너무 짧습니다 (줄 수 부족).")
                continue

            # 데이터 파싱 시도
            lut = []
            # 보통 4~7번째 줄 사이, 혹은 숫자만 있는 줄을 찾아서 파싱
            data_lines_count = 0
            for line in lines:
                # 쉼표나 공백으로 분리해서 숫자가 10개 이상 있는 줄만 데이터로 인정
                parts = [x for x in line.replace(',', ' ').split() if x.strip().replace('-','').isdigit()]
                if len(parts) > 10:
                    lut.extend([int(x) for x in parts])
                    data_lines_count += 1
            
            # [진단 2] 숫자를 못 찾음
            if len(lut) == 0:
                errors.append(f"⚠️ {fname}: 파일 안에서 숫자 데이터를 찾을 수 없습니다.")
                continue

            # [진단 3] 데이터 개수 부족 (RGB LUT는 보통 768개 필요)
            # 하지만 256개만 있는 경우(흑백)도 있으니 3배로 늘려줌
            if len(lut) == 256:
                lut = lut * 3
            
            if len(lut) < 768:
                 # 모자라면 마지막 값으로 채움
                lut += [lut[-1]] * (768 - len(lut))
            else:
                lut = lut[:768] # 넘치면 자름
            
            f_name_clean = os.path.splitext(fname)[0]
            filters[f_name_clean] = lut

        except Exception as e:
            errors.append(f"❌ {fname}: 읽기 중 오류 발생 ({str(e)})")
            
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
st.title("🎞️ CAMPSMAP Pro (진단 모드)")

# ------------------------------------------------
# [진단 결과 표시 구역]
# ------------------------------------------------
loaded_filters, error_logs = load_filters_with_diagnosis()

with st.expander(f"📊 시스템 리포트 (성공: {len(loaded_filters)}개 / 실패: {len(error_logs)}개)", expanded=True):
    if error_logs:
        st.error("👇 아래 파일들은 문제가 있어서 로드되지 않았습니다.")
        for err in error_logs:
            st.write(err)
        st.caption("해결법: 해당 파일의 내용이 올바른지 확인하거나, 다운로드 받은 정품(?) 필터를 다시 올려보세요.")
    else:
        st.success("모든 필터 파일이 완벽하게 로드되었습니다!")
        st.write(f"로드된 필터: {', '.join(list(loaded_filters.keys()))}")

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
                        selections[f_name] = st.checkbox(f"**{f_name}**", key=f"chk_{st.session_state.current_index}_{f_name}")
            else:
                st.error("로드된 필터가 없습니다.")
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
                        final.save(os.path.join(st.session_state.temp_dir, f"{fname_no_ext}_{f_name}.jpg"), quality=95, subsampling=0)
                        st.session_state.saved_files_count += 1
                st.session_state.current_index += 1
                st.rerun()

        if skip:
            st.session_state.current_index += 1
            st.rerun()
