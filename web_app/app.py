import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import shutil
import tempfile
import gc

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Mobile", page_icon="📱")

st.title("📱 CAMPSMAP")
st.markdown("모바일에서도 편하게 쓸 수 있는 버전입니다.")

# --- 세션 초기화 ---
if 'storage_path' not in st.session_state:
    st.session_state['storage_path'] = tempfile.mkdtemp()
    st.session_state['file_count'] = 0

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

# --- 사이드바 (기존 기능 유지) ---
with st.sidebar:
    st.header(f"보관함: {st.session_state['file_count']}장")
    
    # ZIP 파일 미리 생성 (다운로드 준비)
    zip_ready = False
    if st.session_state['file_count'] > 0:
        shutil.make_archive(st.session_state['storage_path'], 'zip', st.session_state['storage_path'])
        zip_ready = True
        
        with open(st.session_state['storage_path'] + ".zip", "rb") as f:
            st.download_button("📥 ZIP 다운로드 (사이드바)", f, "Result.zip", "application/zip")
            
        if st.button("🗑️ 초기화"):
            shutil.rmtree(st.session_state['storage_path'])
            os.makedirs(st.session_state['storage_path'])
            st.session_state['file_count'] = 0
            st.rerun()

# --- 메인 화면 ---
if not loaded_filters:
    st.error("필터 파일이 없습니다!")
else:
    uploaded_files = st.file_uploader("사진 선택", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

    if uploaded_files:
        if st.button(f"🚀 {len(uploaded_files)}장 변환 시작"):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            processed_count = 0
            
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"처리 중... {uploaded_file.name}")
                try:
                    img = Image.open(uploaded_file).convert('RGB')
                    img = ImageOps.exif_transpose(img)
                    img.thumbnail((1500, 1500), Image.Resampling.LANCZOS)
                    
                    img_arr = np.array(img, dtype=np.float32)
                    h, w, c = img_arr.shape
                    
                    # 효과
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
                            base_img.point(lut).save(save_path, quality=90, subsampling=0)
                            processed_count += 1
                        except: pass
                except: pass
                
                gc.collect()
                progress_bar.progress((idx + 1) / len(uploaded_files))
            
            st.session_state['file_count'] += processed_count
            st.success(f"✅ {processed_count}장 완료!")
            
            # [추가됨] 메인 화면에 다운로드 버튼 즉시 표시
            shutil.make_archive(st.session_state['storage_path'], 'zip', st.session_state['storage_path'])
            with open(st.session_state['storage_path'] + ".zip", "rb") as f:
                st.download_button(
                    label="📥 결과물 바로 다운로드 (여기 클릭!)",
                    data=f,
                    file_name="CAMPSMAP_Result.zip",
                    mime="application/zip",
                    type="primary" # 버튼 강조색 적용
                )
    
    # 작업 이력이 있는데 아직 다운로드 안 했을 경우를 위해 메인에도 버튼 표시
    elif st.session_state['file_count'] > 0:
        st.info("👇 이전에 작업한 결과물이 보관함에 있습니다.")
        shutil.make_archive(st.session_state['storage_path'], 'zip', st.session_state['storage_path'])
        with open(st.session_state['storage_path'] + ".zip", "rb") as f:
            st.download_button(
                label="📥 결과물 바로 다운로드",
                data=f,
                file_name="CAMPSMAP_Result.zip",
                mime="application/zip",
                type="primary"
            )
