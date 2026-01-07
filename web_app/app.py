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

st.title("📸 CAMPSMAP (빠른 다운로드)")
st.info("💡 사이드바를 열 필요가 없습니다. 변환 끝나면 여기에 바로 버튼이 뜹니다.")

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

# --- 사이드바 (보조 기능) ---
with st.sidebar:
    st.header(f"📦 누적: {st.session_state['file_count']}장")
    st.caption("새로고침(F5) 하면 초기화됩니다.")
    if st.button("🗑️ 모두 지우기"):
        shutil.rmtree(st.session_state['storage_path'])
        os.makedirs(st.session_state['storage_path'])
        st.session_state['file_count'] = 0
        st.rerun()

# --- 메인 화면 ---
if not loaded_filters:
    st.error("⚠️ 필터 파일이 없습니다!")
else:
    uploaded_files = st.file_uploader("사진을 올려주세요", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

    if uploaded_files:
        # 버튼을 누르면 작업 시작
        if st.button(f"🚀 {len(uploaded_files)}장 변환 시작"):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            processed_now = 0
            
            # 1. 변환 작업
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"처리 중... ({idx+1}/{len(uploaded_files)})")
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
                            base_img.point(lut).save(save_path, quality=92, subsampling=0)
                            processed_now += 1
                        except: pass
                except: pass
                
                gc.collect()
                progress_bar.progress((idx + 1) / len(uploaded_files))
            
            # 2. 작업 완료 후 처리
            st.session_state['file_count'] += processed_now
            status_text.text("✅ 파일 묶는 중... (잠시만요)")
            
            # 3. [핵심] ZIP 파일 즉시 생성 (압축 안함 모드 = 빠름)
            zip_path = os.path.join(st.session_state['storage_path'], "Result.zip")
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                for root, dirs, files in os.walk(st.session_state['storage_path']):
                    for file in files:
                        if file == "Result.zip": continue
                        zipf.write(os.path.join(root, file), arcname=file)
            
            # 4. 다운로드 버튼을 메인 화면에 바로 띄움
            st.success(f"🎉 작업 끝! 아래 버튼을 눌러주세요.")
            
            with open(zip_path, "rb") as f:
                st.download_button(
                    label="📥 결과물 다운로드 (여기를 클릭!)",
                    data=f,
                    file_name="CAMPSMAP_Result.zip",
                    mime="application/zip",
                    type="primary" # 빨간색/강조색 버튼
                )
