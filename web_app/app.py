import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import shutil
import tempfile
import gc
import zipfile

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Final", page_icon="📸")

st.title("📸 CAMPSMAP")

# --- 세션 상태 초기화 (변수들이 새로고침 되어도 지워지지 않게 함) ---
if 'storage_path' not in st.session_state:
    st.session_state['storage_path'] = tempfile.mkdtemp()
if 'file_count' not in st.session_state:
    st.session_state['file_count'] = 0
if 'download_ready' not in st.session_state:
    st.session_state['download_ready'] = False  # 다운로드 준비 완료 여부

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
        if os.path.exists(filter_dir):
            try:
                files = [f for f in os.listdir(filter_dir) if f.lower().endswith(('.fit', '.flt'))]
                for fname in files:
                    full_path = os.path.join(filter_dir, fname)
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    if len(lines) < 7: continue
                    def parse_line(line_str):
                        return [int(x) for x in line_str.replace(',', ' ').split() if x.strip().isdigit()]
                    r = parse_line(lines[4])
                    g = parse_line(lines[5])
                    b = parse_line(lines[6])
                    full_lut = r + g + b
                    if len(full_lut) < 768: full_lut += [full_lut[-1]] * (768 - len(full_lut))
                    else: full_lut = full_lut[:768]
                    filters[os.path.splitext(fname)[0]] = full_lut
            except: continue
    return filters

loaded_filters = load_filters()

# --- 사이드바 ---
with st.sidebar:
    st.header(f"📦 보관함: {st.session_state['file_count']}장")
    if st.button("🗑️ 처음으로 (초기화)"):
        shutil.rmtree(st.session_state['storage_path'], ignore_errors=True)
        st.session_state['storage_path'] = tempfile.mkdtemp()
        st.session_state['file_count'] = 0
        st.session_state['download_ready'] = False
        st.rerun()

# --- 메인 로직 ---

# 1. 다운로드 준비가 완료된 상태라면? -> 결과 화면 보여주기
if st.session_state['download_ready']:
    st.success(f"🎉 작업 완료! 총 {st.session_state['file_count']}장이 준비되었습니다.")
    
    zip_path = os.path.join(st.session_state['storage_path'], "Result.zip")
    
    # 파일이 실제로 있는지 확인 후 버튼 표시
    if os.path.exists(zip_path):
        with open(zip_path, "rb") as f:
            st.download_button(
                label="📥 결과물 다운로드 (여기를 클릭)",
                data=f,
                file_name="CAMPSMAP_Result.zip",
                mime="application/zip",
                type="primary"
            )
    else:
        st.error("파일 생성 중 오류가 발생했습니다. 초기화 후 다시 시도해주세요.")
        
    st.info("새로운 사진을 작업하려면 사이드바의 '초기화' 버튼을 누르세요.")

# 2. 아직 작업 전이라면? -> 업로드 화면 보여주기
else:
    if not loaded_filters:
        st.error("⚠️ 필터 파일이 없습니다!")
    else:
        st.info("사진을 업로드하면 변환 후 다운로드 버튼이 나타납니다.")
        uploaded_files = st.file_uploader("사진 선택", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

        if uploaded_files:
            if st.button(f"🚀 {len(uploaded_files)}장 변환 시작"):
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                processed_now = 0
                
                # 변환 루프
                for idx, uploaded_file in enumerate(uploaded_files):
                    status_text.text(f"처리 중... ({idx+1}/{len(uploaded_files)})")
                    try:
                        img = Image.open(uploaded_file).convert('RGB')
                        img = ImageOps.exif_transpose(img)
                        img.thumbnail((1500, 1500), Image.Resampling.LANCZOS)
                        
                        img_arr = np.array(img, dtype=np.float32)
                        h, w, c = img_arr.shape
                        
                        # 효과 적용
                        noise = np.random.normal(0, 12, (h, w, 1)).repeat(3, axis=2)
                        x = np.linspace(-1, 1, w)
                        y = np.linspace(-1, 1, h)
                        X, Y = np.meshgrid(x, y)
                        mask = (1 - np.clip(np.sqrt(X**2 + Y**2) - 0.5, 0, 1) * 0.4)[:, :, np.newaxis].repeat(3, axis=2)
                        img_arr = (img_arr + noise) * mask
                        base_img = Image.fromarray(np.clip(img_arr, 0, 255).astype(np.uint8))
                        
                        fname_prefix = os.path.splitext(uploaded_file.name)[0]
                        for fname, lut in loaded_filters.items():
                            try:
                                save_path = os.path.join(st.session_state['storage_path'], f"{fname_prefix}_{fname}.jpg")
                                base_img.point(lut).save(save_path, quality=92, subsampling=0)
                                processed_now += 1
                            except: pass
                    except: pass
                    
                    gc.collect()
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                
                # 변환 끝
                st.session_state['file_count'] += processed_now
                
                # ZIP 파일 생성 (압축 안 함 = 속도 빠름)
                status_text.text("파일 묶는 중...")
                zip_path = os.path.join(st.session_state['storage_path'], "Result.zip")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                    for root, dirs, files in os.walk(st.session_state['storage_path']):
                        for file in files:
                            if file == "Result.zip": continue
                            zipf.write(os.path.join(root, file), arcname=file)
                
                # 상태 변경 후 새로고침 -> 위쪽의 'if download_ready:' 블록이 실행됨
                st.session_state['download_ready'] = True
                st.rerun()
