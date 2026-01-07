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
1. 사진을 업로드하고 **[변환 및 보관함에 추가]**를 누르세요.
2. RAM을 비우고 보관함(Disk)에 결과물을 차곡차곡 쌓습니다.
3. 모든 작업이 끝나면 사이드바에서 **[ZIP 다운로드]**를 하세요.
""")

# --- 세션 스테이트 초기화 (보관함 만들기) ---
if 'storage_path' not in st.session_state:
    # 임시 폴더 생성
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
    # 1. RGB 변환
    if image.mode != 'RGB': 
        image = image.convert('RGB')
    
    # 2. 리사이징 (중요: 속도 및 메모리 보호)
    # 긴 축을 2500px로 줄임 (필름 감성에는 충분한 화질)
    image.thumbnail((2500, 2500), Image.Resampling.LANCZOS)
    
    # 3. NumPy 변환 및 베이스 효과 (그레인/비네팅)
    img_arr = np.array(image, dtype=np.float32)
    h, w, c = img_arr.shape
    
    # 노이즈 (Grain)
    noise = np.random.normal(0, 12, (h, w))
    noise = np.repeat(noise[:, :, np.newaxis], 3, axis=2)
    
    # 비네팅 (Vignette)
    x = np.linspace(-1, 1, w)
    y = np.linspace(-1, 1, h)
    X, Y = np.meshgrid(x, y)
    radius = np.sqrt(X**2 + Y**2)
    mask = 1 - np.clip(radius - 0.5, 0, 1) * 0.4
    mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    
    # 효과 적용
    img_arr = (img_arr + noise) * mask
    img_arr = np.clip(img_arr, 0, 255).astype(np.uint8)
    
    # 베이스 이미지 객체 생성
    base_img = Image.fromarray(img_arr)
    
    # 4. 필터 적용 및 저장
    saved_count = 0
    for filter_name, lut_data in loaded_filters.items():
        try:
            # LUT 적용
            final = base_img.point(lut_data)
            
            # 파일 저장
            save_name = f"{filename_prefix}_{filter_name}.jpg"
            save_path = os.path.join(save_dir, save_name)
            
            # subsampling=0 : 고화질 JPG 저장
            final.save(save_path, quality=95, subsampling=0)
            saved_count += 1
            
            # 메모리 해제
            del final
        except:
            continue
            
    return saved_count

# --- 메인 로직 ---
loaded_filters = load_filters()

# 사이드바: 보관함 및 다운로드
with st.sidebar:
    st.header(f"📦 보관함: {st.session_state['file_count']}장")
    st.caption(f"임시 경로: {st.session_state['storage_path']}")
    
    # 보관함에 파일이 있을 때만 다운로드 버튼 표시
    if st.session_state['file_count'] > 0:
        st.divider()
        st.write("작업이 끝났으면 다운로드하세요.")
        
        # ZIP 압축 파일 생성 (매번 새로 압축하지 않도록 버튼 누를 때 로직 처리 권장하지만, 간편함을 위해 여기 배치)
        shutil.make_archive(st.session_state['storage_path'], 'zip', st.session_state['storage_path'])
        zip_file_path = st.session_state['storage_path'] + ".zip"
        
        with open(zip_file_path, "rb") as f:
            st.download_button(
                label="📥 전체 ZIP 다운로드",
                data=f,
                file_name="CAMPSMAP_Result.zip",
                mime="application/zip"
            )
            
        st.divider()
        if st.button("🗑️ 보관함 비우기 (초기화)"):
            shutil.rmtree(st.session_state['storage_path'])
            os.makedirs(st.session_state['storage_path'])
            st.session_state['file_count'] = 0
            st.rerun()

# 메인 화면: 업로더
if not loaded_filters:
    st.error("⚠️ 서버에 필터 파일이 없습니다. (Filters 폴더를 확인하세요)")
else:
    st.info("💡 사진을 여러 번 나눠서 올려도 됩니다. 모두 합쳐서 다운로드됩니다.")
    
    # 업로더 Key를 동적으로 관리하여 처리 후 자동 초기화
    dynamic_key = st.session_state['uploader_key']
    uploaded_files = st.file_uploader(
        "사진 추가 (Drag & Drop)", 
        type=['png', 'jpg', 'jpeg'], 
        accept_multiple_files=True,
        key=dynamic_key
    )

    if uploaded_files:
        if st.button(f"🚀 {len(uploaded_files)}장 변환 시작"):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            total_files = len(uploaded_files)
            processed_now = 0
            
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"처리 중... ({idx+1}/{total_files}) : {uploaded_file.name}")
                
                try:
                    # 이미지 열기
                    image = Image.open(uploaded_file)
                    image = ImageOps.exif_transpose(image) # 회전 정보 보정
                    
                    # 파일명 추출
                    filename_prefix = os.path.splitext(uploaded_file.name)[0]
                    
                    # 처리 및 저장 함수 호출
                    count = process_and_save(
                        image, 
                        st.session_state['storage_path'], 
                        filename_prefix, 
                        loaded_filters
                    )
                    processed_now += count
                    
                except Exception as e:
                    st.error(f"오류 발생 ({uploaded_file.name}): {e}")
                
                # 메모리 강제 정리 (대량 작업 시 필수)
                gc.collect()
                
                # 진행률 업데이트
                progress_bar.progress((idx + 1) / total_files)
            
            # 작업 완료 후 처리
            st.session_state['file_count'] += processed_now
            st.session_state['uploader_key'] += 1 # 키를 변경하여 업로더 초기화
            
            status_text.success(f"✅ 방금 {processed_now}장의 사진이 보관함에 추가되었습니다!")
            
            # 화면 갱신 (업로더 비우고 사이드바 카운트 업데이트)
            st.rerun()
