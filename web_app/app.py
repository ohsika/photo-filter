import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import shutil
import tempfile
import gc
import zipfile  # zipfile 모듈 직접 사용

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Speed Lab", page_icon="⚡")

st.title("⚡ CAMPSMAP (고속 다운로드)")
st.markdown("사진을 변환하고 **압축 없이 빠르게 묶어서** 다운로드합니다.")

# --- 세션 초기화 ---
if 'storage_path' not in st.session_state:
    st.session_state['storage_path'] = tempfile.mkdtemp()
    st.session_state['file_count'] = 0
    st.session_state['zip_ready'] = False # ZIP 준비 여부 확인

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

# --- 사이드바 (다운로드 로직 개선) ---
with st.sidebar:
    st.header(f"📦 보관함: {st.session_state['file_count']}장")
    
    if st.session_state['file_count'] > 0:
        st.write("---")
        
        # [핵심 변경] 사용자가 버튼을 눌러야만 압축 시작 (무한 로딩 방지)
        if st.button("🎁 다운로드 파일 생성하기"):
            zip_path = st.session_state['storage_path'] + ".zip"
            folder_path = st.session_state['storage_path']
            
            with st.spinner("파일 묶는 중... (압축 안 함 = 빠름)"):
                # ZIP_STORED: 압축하지 않고 그냥 담기만 함 (속도 매우 빠름)
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                    for root, dirs, files in os.walk(folder_path):
                        for file in files:
                            # 이미 생성된 zip 파일은 제외
                            if file.endswith(".zip"): continue
                            file_path = os.path.join(root, file)
                            zipf.write(file_path, arcname=file)
            
            st.session_state['zip_ready'] = True
            st.success("생성 완료!")

        # ZIP 파일이 준비되었을 때만 다운로드 버튼 표시
        if st.session_state.get('zip_ready'):
            zip_file_path = st.session_state['storage_path'] + ".zip"
            if os.path.exists(zip_file_path):
                with open(zip_file_path, "rb") as f:
                    st.download_button(
                        label="📥 ZIP 다운로드 (여기를 클릭)",
                        data=f,
                        file_name="Result.zip",
                        mime="application/zip",
                        type="primary"
                    )

        st.write("---")
        if st.button("🗑️ 초기화"):
            shutil.rmtree(st.session_state['storage_path'])
            os.makedirs(st.session_state['storage_path'])
            st.session_state['file_count'] = 0
            st.session_state['zip_ready'] = False
            st.rerun()

# --- 메인 화면 ---
if not loaded_filters:
    st.error("⚠️ 필터 파일 없음")
else:
    uploaded_files = st.file_uploader("사진 선택", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

    if uploaded_files:
        if st.button(f"🚀 {len(uploaded_files)}장 변환 시작"):
            
            progress_bar = st.progress(0)
            processed_now = 0
            
            for idx, uploaded_file in enumerate(uploaded_files):
                try:
                    img = Image.open(uploaded_file).convert('RGB')
                    img = ImageOps.exif_transpose(img)
                    img.thumbnail((1500, 1500), Image.Resampling.LANCZOS)
                    
                    img_arr = np.array(img, dtype=np.float32)
                    h, w, c = img_arr.shape
                    
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
            
            st.session_state['file_count'] += processed_now
            # 변환 후 ZIP 상태 초기화 (새 파일이 들어왔으므로 다시 묶어야 함)
            st.session_state['zip_ready'] = False 
            st.success(f"✅ 변환 끝! 사이드바에서 '다운로드 파일 생성하기' 버튼을 누르세요.")
            
            # 페이지 새로고침 제거 (메시지 유지)
            # st.rerun()
