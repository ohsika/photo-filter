import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import shutil
import tempfile
import gc

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Unlimited", page_icon="📸")

st.title("📸 CAMPSMAP (무제한 적립 모드)")
st.markdown("""
**대용량 처리 전용 모드입니다.**
1. 사진을 나눠서 업로드하고 **[변환 및 보관함에 추가]**를 누르세요.
2. RAM을 비우고 보관함(Disk)에 결과물을 쌓아둡니다.
3. 다 끝났으면 사이드바에서 **[ZIP 다운로드]**를 누르세요.
""")

# --- 세션 스테이트 초기화 (보관함 만들기) ---
if 'storage_path' not in st.session_state:
    # 임시 폴더 생성 (서버 디스크 사용)
    temp_dir = tempfile.mkdtemp()
    st.session_state['storage_path'] = temp_dir
    st.session_state['file_count'] = 0
    st.session_state['uploader_key'] = 0 # 업로더 초기화용 키

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
    valid_extensions = ('.fit', '.flt')

    for filter_dir in possible_paths:
        if not os.path.exists(filter_dir): continue
        try:
            files = [f for f in os.listdir(filter_dir) if f.lower().endswith(valid_extensions)]
            for fname in files:
                filter_name = os.path.splitext(fname)[0]
                if filter_name in filters: continue
                full_path = os.path.join(filter_dir, fname)
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                if len(lines) < 7: continue
                def parse_line(line_str):
                    return [int(x) for x in line_str.replace(',', ' ').split() if x.strip().isdigit()]
                r_lut = parse_line(lines[4])
                g_lut = parse_line(lines[5])
                b_lut = parse_line(lines[6])
                full_lut = r_lut + g_lut + b_lut
                if len(full_lut) < 768: full_lut += [full_lut[-1]] * (768 - len(full_lut))
                else: full_lut = full_lut[:768]
                filters[filter_name] = full_lut
        except: pass
    return filters

# --- 이미지 처리 함수 ---
def process_and_save(image, save_dir, filename_prefix, loaded_filters):
    # RGB 변환
    if image.mode != 'RGB': image = image.convert('RGB')
    
    # NumPy 변환
    img_arr = np.array(image, dtype=np.float32)
    
    # 그레인 & 비네팅 (베이스 효과)
    h, w, c = img_arr.shape
    noise = np.random.normal(0, 12, (h, w)) # 노이즈
    noise = np.repeat(noise[:, :, np.newaxis], 3, axis=2)
    
    x = np.linspace(-1, 1, w)
    y = np.linspace(-1, 1, h)
    X, Y = np.meshgrid(x, y)
    radius = np.sqrt(X**2 + Y**2)
    mask = 1 - np.clip(radius - 0.5, 0, 1) * 0.4 # 비네팅
    mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    
    img_arr = (img_arr + noise) * mask
    img_arr = np.clip(img_arr, 0, 255).astype(np.uint8)
    
    # 베이스 이미지 생성
    base_img = Image.fromarray(img_arr)
    
    # 필터 적용 및 저장
    saved_count = 0
    for filter_name, lut_data in loaded_filters.items():
        try:
            final = base_img.point(lut_data)
            
            save_name = f"{filename_prefix}_{filter_name}.jpg"
            save_path = os.path.join(save_dir, save_name)
            
            final.save(save_path, quality=92, subsampling=0)
            saved_count += 1
            del final
        except:
            continue
            
    return saved_count

# --- 메인 로직 ---
loaded_filters = load_filters()
if not loaded_filters:
    st.warning("⚠️ 필터 파일 없음 (Filters 폴더 확인)")

# 사이드바: 보관함 상태 표시
with st.sidebar:
    st.header(f"📦 보관함: {st.session_state['file_count']}장")
    st.caption(f"저장 위치: {st.session_state['storage_path']}")
    
    if st.session_state['file_count'] > 0:
        if st.button("🗑️ 보관함 비우기 (초기화)"):
            shutil.rmtree(st.session_state['storage_path'])
            os.makedirs(st.session_state['storage_path'])
            st.session_state['file_count'] = 0
            st.rerun()
            
        st.divider()
        st.write("작업이 모두 끝났으면 다운로드하세요.")
        
        # 압축 및 다운로드 버튼
        shutil.make_archive(st.session_state['storage_path'], 'zip', st.session_state['storage_path'])
        zip_path = st.session_state['storage_path'] + ".zip"
        
        with open(zip_path, "rb") as f:
            st.download_button(
                label="📥 전체 ZIP 다운로드",
                data=f,
                file_name="CAMPSMAP_Full_Batch.zip",
                mime="application/zip"
            )

# 메인 화면: 업로드 및 변환
st.info("💡 50장씩 끊어서 올리면 절대 멈추지 않습니다. 계속 추가하세요!")

# key를 변경해서 업로더를 강제로 초기화하는 기술
uploader_key = f"uploader_{st.session_state['uploader_key']}"
uploaded_files = st.file_uploader("사진 추가 (여러 장 가능)", 
                                  type=['png', 'jpg', 'jpeg'], 
                                  accept_multiple_files=True,
                                  key=uploader_key)

if uploaded_files and loaded_filters:
    if st.button(f"🚀 {len(uploaded_files)}장 변환 및 보관함에 추가"):
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_files = len(uploaded_files)
        current_batch_count = 0
        
        for idx, uploaded_file in enumerate(uploaded_files):
            try:
                status_text.text(f"처리 중 ({idx+1}/{total_files}): {uploaded_file.name}")
                progress_bar.progress((idx) / total_files)
                
                # 이미지 열기
                image = Image.open(uploaded_file)
                image = ImageOps.exif_transpose(image)
                
                # 안전장치: 초고해상도 리사이징 (서버 보호)
                if image.width > 4000 or image.height > 4000:
                    image.thumbnail((4000, 4000), Image.Resampling.LANCZOS)
                
                file_prefix = os.path.splitext(uploaded_file.name)[0]
                
                # 처리 및 저장 (Disk에 바로 씀)
                count = process_and_save(image, st.session_state['storage_path'], file_prefix, loaded_filters)
                current_batch_count += count
                
                # 메모리 청소
                del image
                gc.collect()
                
            except Exception as e:
                st.error(f"오류 ({uploaded_file.name}): {e}")
                continue
                
        # 배치 작업 완료 후 처리
        st.session_state['file_count'] += current_batch_count
        st.session_state['uploader_key'] += 1 # 키를 바꿔서 업로더 초기화
        
        st.success(f"✅ {len(uploaded_files)}장 처리 완료! 보관함에 총 {st.session_state['file_count']}장이 쌓였습니다.")
        st.rerun() # 화면 새로고침해서 업로더 비우기
