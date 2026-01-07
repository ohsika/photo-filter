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
st.set_page_config(page_title="CAMPSMAP Debug", page_icon="🛠️")

st.title("📸 CAMPSMAP (진단 모드)")
st.info("💡 이제 필터 로딩 여부와 상관없이 **업로더가 무조건 표시됩니다.**")

# --- 세션 초기화 ---
if 'storage_path' not in st.session_state:
    st.session_state['storage_path'] = tempfile.mkdtemp()
if 'file_count' not in st.session_state:
    st.session_state['file_count'] = 0
if 'uploader_key' not in st.session_state:
    st.session_state['uploader_key'] = 0

# --- 필터 로딩 (진단 기능 추가) ---
@st.cache_data
def load_filters():
    filters = {}
    debug_logs = []
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [
        os.path.join(current_dir, "Filters"),
        os.path.join(current_dir, "web_app", "Filters"),
        "Filters",
        "." # 현재 폴더까지 검색
    ]
    
    for filter_dir in possible_paths:
        if os.path.exists(filter_dir):
            debug_logs.append(f"✅ 폴더 찾음: {filter_dir}")
            try:
                files = [f for f in os.listdir(filter_dir) if f.lower().endswith(('.fit', '.flt'))]
                if not files:
                    debug_logs.append(f"   -> ⚠️ 폴더는 있는데 .fit/.flt 파일이 없음")
                
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
            except Exception as e:
                debug_logs.append(f"   -> ❌ 에러: {e}")
        else:
            debug_logs.append(f"❌ 폴더 없음: {filter_dir}")
            
    return filters, debug_logs

loaded_filters, logs = load_filters()

# --- 디버깅 창 (문제가 뭔지 보여줌) ---
with st.expander("🛠️ 필터 연결 상태 확인 (클릭)", expanded=False):
    for log in logs:
        st.text(log)
    st.write(f"**총 로드된 필터 개수: {len(loaded_filters)}개**")

if not loaded_filters:
    st.error("⚠️ 필터를 찾지 못했습니다! 하지만 업로더는 표시해드립니다.")
    st.warning("위의 [필터 연결 상태 확인]을 눌러서 경로를 확인해보세요.")

# --- 사이드바 ---
with st.sidebar:
    st.header(f"📦 누적: {st.session_state['file_count']}장")
    
    # 다운로드 섹션
    if st.session_state['file_count'] > 0:
        st.divider()
        st.subheader("📥 다운로드")
        
        all_files = [f for f in os.listdir(st.session_state['storage_path']) if f.lower().endswith('.jpg')]
        all_files.sort()
        
        chunk_size = 50
        total_chunks = math.ceil(len(all_files) / chunk_size)
        
        for i in range(total_chunks):
            start = i * chunk_size
            end = start + chunk_size
            chunk_files = all_files[start:end]
            part_num = i + 1
            zip_name = f"Result_Part_{part_num}.zip"
            zip_path = os.path.join(st.session_state['storage_path'], zip_name)
            
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
    if st.button("🗑️ 초기화"):
        try: shutil.rmtree(st.session_state['storage_path'])
        except: pass
        st.session_state['storage_path'] = tempfile.mkdtemp()
        st.session_state['file_count'] = 0
        st.session_state['uploader_key'] += 1
        gc.collect()
        st.rerun()

# --- 메인 화면 (업로더 무조건 표시) ---
uploader_key = f"uploader_{st.session_state['uploader_key']}"

uploaded_files = st.file_uploader(
    "사진을 여기에 추가하세요 (무한 업로드 가능)", 
    type=['png', 'jpg', 'jpeg'], 
    accept_multiple_files=True,
    key=uploader_key
)

if uploaded_files:
    if not loaded_filters:
        st.error("❌ 필터 파일이 없어서 변환을 시작할 수 없습니다.")
    else:
        if st.button(f"🚀 {len(uploaded_files)}장 변환 및 저장"):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            processed_now = 0
            
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"처리 중... ({idx+1}/{len(uploaded_files)})")
                try:
                    img = Image.open(uploaded_file).convert('RGB')
                    img = ImageOps.exif_transpose(img)
                    img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                    
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
                            base_img.point(lut).save(save_path, quality=90, subsampling=1)
                            processed_now += 1
                        except: pass
                    
                    del base_img
                    
                except: pass
                
                gc.collect()
                progress_bar.progress((idx + 1) / len(uploaded_files))
            
            st.session_state['file_count'] += processed_now
            st.session_state['uploader_key'] += 1
            
            st.success(f"✅ {processed_now}장 저장 완료! (누적: {st.session_state['file_count']}장)")
            st.rerun()
