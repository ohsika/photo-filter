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

st.title("📸 CAMPSMAP (통합 모드)")
st.info("💡 **사진 추가** -> **변환** -> **아래에서 다운로드** 순서로 진행하세요.")

# --- 세션 상태 초기화 ---
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

# --- 사이드바 (초기화) ---
with st.sidebar:
    st.header(f"📦 누적: {st.session_state['file_count']}장")
    st.caption("작업이 꼬이면 초기화하세요.")
    if st.button("🗑️ 싹 지우고 새로하기"):
        try: shutil.rmtree(st.session_state['storage_path'])
        except: pass
        st.session_state['storage_path'] = tempfile.mkdtemp()
        st.session_state['file_count'] = 0
        gc.collect()
        st.rerun()

# --- 1. 업로드 및 변환 섹션 (항상 보임) ---
if not loaded_filters:
    st.error("⚠️ 필터 파일이 없습니다!")
else:
    # key를 매번 바꿔주지 않아도 되도록 구조 변경
    uploaded_files = st.file_uploader("사진을 여기에 계속 추가하세요", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

    if uploaded_files:
        if st.button(f"🚀 {len(uploaded_files)}장 변환 및 추가하기"):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            processed_now = 0
            
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"처리 중... ({idx+1}/{len(uploaded_files)})")
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
                            base_img.point(lut).save(save_path, quality=90, subsampling=0)
                            processed_now += 1
                        except: pass
                except: pass
                
                del img, img_arr, base_img
                gc.collect()
                progress_bar.progress((idx + 1) / len(uploaded_files))
            
            st.session_state['file_count'] += processed_now
            st.success(f"✅ {processed_now}장 추가 완료! (총 {st.session_state['file_count']}장)")
            
            # 새로고침 (업로더 비우고 결과창 갱신)
            st.rerun()

# --- 2. 다운로드 섹션 (결과물이 있을 때만 보임) ---
st.divider()

if st.session_state['file_count'] > 0:
    st.subheader("📥 결과물 다운로드")
    st.write("서버 오류 방지를 위해 **50장씩 나누어** 포장해뒀습니다.")
    
    # 파일 목록 갱신
    all_files = [f for f in os.listdir(st.session_state['storage_path']) if f.lower().endswith('.jpg')]
    all_files.sort()
    
    # 50장씩 나누기
    chunk_size = 50
    total_chunks = math.ceil(len(all_files) / chunk_size)
    
    # 버튼 나열
    cols = st.columns(min(3, max(1, total_chunks))) # 보기 좋게 컬럼으로 배치
    
    for i in range(total_chunks):
        start_idx = i * chunk_size
        end_idx = start_idx + chunk_size
        chunk_files = all_files[start_idx:end_idx]
        
        part_num = i + 1
        zip_name = f"Result_Part_{part_num}.zip"
        zip_path = os.path.join(st.session_state['storage_path'], zip_name)
        
        # 즉석 ZIP핑 (압축 안 함 = 빠름)
        if not os.path.exists(zip_path):
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                for file in chunk_files:
                    file_path = os.path.join(st.session_state['storage_path'], file)
                    zipf.write(file_path, arcname=file)
        
        with open(zip_path, "rb") as f:
            # 컬럼에 나눠서 버튼 배치
            with cols[i % 3]:
                st.download_button(
                    label=f"📦 {part_num}번 파일 받기",
                    data=f,
                    file_name=zip_name,
                    mime="application/zip",
                    key=f"dl_btn_{i}"
                )
