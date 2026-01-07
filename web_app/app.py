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
st.set_page_config(page_title="CAMPSMAP Infinity", page_icon="♾️")

st.title("♾️ CAMPSMAP (이어하기 모드)")
st.info("""
**[사용법]**
1. 한 번에 **30~50장씩**만 올리고 변환하세요. (서버 다운 방지)
2. 변환이 끝나면 업로더가 **자동으로 비워집니다.**
3. **계속해서 다음 사진을 올리세요.** (결과물은 계속 누적됩니다.)
4. 다 끝났으면 **왼쪽 사이드바**에서 다운로드하세요.
""")

# --- 세션 초기화 ---
if 'storage_path' not in st.session_state:
    st.session_state['storage_path'] = tempfile.mkdtemp()
if 'file_count' not in st.session_state:
    st.session_state['file_count'] = 0
# [핵심] 업로더를 강제로 리셋하기 위한 키
if 'uploader_key' not in st.session_state:
    st.session_state['uploader_key'] = 0

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

# --- 사이드바 (다운로드 & 초기화) ---
with st.sidebar:
    st.header(f"📦 누적: {st.session_state['file_count']}장")
    
    # 결과물이 있을 때만 다운로드 버튼 표시
    if st.session_state['file_count'] > 0:
        st.divider()
        st.subheader("📥 다운로드 (분할)")
        
        all_files = [f for f in os.listdir(st.session_state['storage_path']) if f.lower().endswith('.jpg')]
        all_files.sort()
        
        # 50장씩 끊기 (안정성)
        chunk_size = 50
        total_chunks = math.ceil(len(all_files) / chunk_size)
        
        st.caption(f"총 {total_chunks}개 파일로 나눴습니다.")
        
        for i in range(total_chunks):
            start = i * chunk_size
            end = start + chunk_size
            chunk_files = all_files[start:end]
            
            part_num = i + 1
            zip_name = f"Result_Part_{part_num}.zip"
            zip_path = os.path.join(st.session_state['storage_path'], zip_name)
            
            # ZIP 없으면 생성 (표준 압축)
            if not os.path.exists(zip_path):
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file in chunk_files:
                        file_path = os.path.join(st.session_state['storage_path'], file)
                        zipf.write(file_path, arcname=file)
            
            with open(zip_path, "rb") as f:
                st.download_button(
                    label=f"📦 {part_num}번 파일 ({len(chunk_files)}장)",
                    data=f,
                    file_name=zip_name,
                    mime="application/zip",
                    key=f"dl_{i}"
                )

    st.divider()
    if st.button("🗑️ 처음부터 다시 하기 (초기화)"):
        try: shutil.rmtree(st.session_state['storage_path'])
        except: pass
        st.session_state['storage_path'] = tempfile.mkdtemp()
        st.session_state['file_count'] = 0
        st.session_state['uploader_key'] += 1 # 키 변경으로 업로더 초기화
        gc.collect()
        st.rerun()

# --- 메인 화면 ---
if not loaded_filters:
    st.error("⚠️ 필터 파일이 없습니다!")
else:
    # [핵심] key를 매번 바꿔줘서 업로더 내부 메모리를 강제로 비움
    uploader_key = f"uploader_{st.session_state['uploader_key']}"
    
    uploaded_files = st.file_uploader(
        "사진 추가 (30~50장씩 권장)", 
        type=['png', 'jpg', 'jpeg'], 
        accept_multiple_files=True,
        key=uploader_key
    )

    if uploaded_files:
        if st.button(f"🚀 {len(uploaded_files)}장 변환 및 저장"):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            processed_now = 0
            
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"처리 중... ({idx+1}/{len(uploaded_files)})")
                try:
                    # 1. 이미지 열기 & 리사이징 (1280px)
                    img = Image.open(uploaded_file).convert('RGB')
                    img = ImageOps.exif_transpose(img)
                    img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                    
                    img_arr = np.array(img, dtype=np.float32)
                    h, w, c = img_arr.shape
                    
                    # 2. 효과 적용
                    noise = np.random.normal(0, 12, (h, w, 1)).repeat(3, axis=2)
                    x = np.linspace(-1, 1, w)
                    y = np.linspace(-1, 1, h)
                    X, Y = np.meshgrid(x, y)
                    mask = (1 - np.clip(np.sqrt(X**2 + Y**2) - 0.5, 0, 1) * 0.4)[:, :, np.newaxis].repeat(3, axis=2)
                    
                    img_arr = (img_arr + noise) * mask
                    base_img = Image.fromarray(np.clip(img_arr, 0, 255).astype(np.uint8))
                    
                    # 메모리 정리
                    del img, img_arr, noise, X, Y, mask
                    
                    # 3. 필터 적용 및 디스크 저장
                    fname_prefix = os.path.splitext(uploaded_file.name)[0]
                    for fname, lut in loaded_filters.items():
                        try:
                            save_path = os.path.join(st.session_state['storage_path'], f"{fname_prefix}_{fname}.jpg")
                            base_img.point(lut).save(save_path, quality=90, subsampling=1)
                            processed_now += 1
                        except: pass
                    
                    del base_img
                    
                except: pass
                
                gc.collect() # 램 청소
                progress_bar.progress((idx + 1) / len(uploaded_files))
            
            # 작업 완료 후 처리
            st.session_state['file_count'] += processed_now
            st.session_state['uploader_key'] += 1 # [중요] 키를 바꿔서 업로더 초기화
            
            st.success(f"✅ {processed_now}장 저장 완료! (현재 누적: {st.session_state['file_count']}장)")
            st.info("업로더가 초기화되었습니다. 다음 사진들을 올려주세요.")
            
            # 새로고침 (업로더가 텅 빈 상태로 다시 나옴)
            st.rerun()
