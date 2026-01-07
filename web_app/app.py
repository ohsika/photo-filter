import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import shutil
import tempfile
import gc
import zipfile
import math

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Final", page_icon="📸")

st.title("📸 CAMPSMAP (안전/고속)")
st.info("💡 **100장씩** 묶어서 포장합니다. (서버 다운 방지 + 버튼 개수 최소화)")

# --- 세션 초기화 ---
if 'storage_path' not in st.session_state:
    st.session_state['storage_path'] = tempfile.mkdtemp()
if 'file_count' not in st.session_state:
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

# --- 사이드바 ---
with st.sidebar:
    st.header(f"📦 완료: {st.session_state['file_count']}장")
    if st.button("🗑️ 초기화"):
        try: shutil.rmtree(st.session_state['storage_path'])
        except: pass
        st.session_state['storage_path'] = tempfile.mkdtemp()
        st.session_state['file_count'] = 0
        gc.collect()
        st.rerun()

# --- 메인 화면 ---
if not loaded_filters:
    st.error("⚠️ 필터 파일 없음")
else:
    # 1. 업로더
    uploaded_files = st.file_uploader("사진 추가", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

    # 2. 변환 로직
    if uploaded_files:
        if st.button(f"🚀 {len(uploaded_files)}장 변환 시작"):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            processed_now = 0
            
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"처리 중... ({idx+1}/{len(uploaded_files)})")
                try:
                    img = Image.open(uploaded_file).convert('RGB')
                    img = ImageOps.exif_transpose(img)
                    # 1000px 리사이징 (램 절약 필수)
                    img.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
                    
                    img_arr = np.array(img, dtype=np.float32)
                    h, w, c = img_arr.shape
                    
                    noise = np.random.normal(0, 12, (h, w, 1)).repeat(3, axis=2)
                    x = np.linspace(-1, 1, w)
                    y = np.linspace(-1, 1, h)
                    X, Y = np.meshgrid(x, y)
                    mask = (1 - np.clip(np.sqrt(X**2 + Y**2) - 0.5, 0, 1) * 0.4)[:, :, np.newaxis].repeat(3, axis=2)
                    
                    img_arr = (img_arr + noise) * mask
                    base_img = Image.fromarray(np.clip(img_arr, 0, 255).astype(np.uint8))
                    
                    del img, img_arr, noise, X, Y, mask
                    
                    fname_prefix = os.path.splitext(uploaded_file.name)[0]
                    for fname, lut in loaded_filters.items():
                        try:
                            save_path = os.path.join(st.session_state['storage_path'], f"{fname_prefix}_{fname}.jpg")
                            # subsampling=1 (용량 절약)
                            base_img.point(lut).save(save_path, quality=90, subsampling=1)
                            processed_now += 1
                        except: pass
                    
                    del base_img
                    
                except: pass
                
                gc.collect()
                progress_bar.progress((idx + 1) / len(uploaded_files))
            
            st.session_state['file_count'] += processed_now
            st.success(f"✅ 변환 완료! (누적 {st.session_state['file_count']}장)")
            st.rerun()

    # 3. 다운로드 섹션
    if st.session_state['file_count'] > 0:
        st.divider()
        st.subheader("📥 결과물 다운로드")
        
        all_files = [f for f in os.listdir(st.session_state['storage_path']) if f.lower().endswith('.jpg')]
        all_files.sort()
        
        if not all_files:
            st.warning("파일이 없습니다.")
        else:
            # 100장씩 나누기 (황금 밸런스)
            chunk_size = 100
            total_chunks = math.ceil(len(all_files) / chunk_size)
            
            st.info(f"총 {len(all_files)}장을 **{total_chunks}개 파일**로 정리했습니다.")
            
            cols = st.columns(min(2, max(1, total_chunks)))
            
            for i in range(total_chunks):
                start = i * chunk_size
                end = start + chunk_size
                chunk_files = all_files[start:end]
                
                part_num = i + 1
                zip_name = f"Result_Part_{part_num}.zip"
                zip_path = os.path.join(st.session_state['storage_path'], zip_name)
                
                # [핵심] ZIP_STORED 사용 (압축 안 함 -> CPU/RAM 사용량 0에 수렴 -> 뻑 안 남)
                if not os.path.exists(zip_path):
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                        for file in chunk_files:
                            file_path = os.path.join(st.session_state['storage_path'], file)
                            zipf.write(file_path, arcname=file)
                
                # 파일 생성 확인 후 버튼 표시
                if os.path.exists(zip_path):
                    with open(zip_path, "rb") as f:
                        with cols[i % 2]:
                            st.download_button(
                                label=f"📦 {part_num}번 ({len(chunk_files)}장)",
                                data=f,
                                file_name=zip_name,
                                mime="application/zip",
                                key=f"dl_btn_{i}"
                            )
