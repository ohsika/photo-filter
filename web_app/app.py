import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import shutil
import tempfile
import gc
import zipfile

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Safe", page_icon="🛡️")

st.title("🛡️ CAMPSMAP (안전 모드)")
st.info("💡 서버가 뻗지 않도록 최적화된 모드입니다. (1280px 리사이징)")

# --- 세션 상태 초기화 ---
if 'storage_path' not in st.session_state:
    st.session_state['storage_path'] = tempfile.mkdtemp()
if 'file_count' not in st.session_state:
    st.session_state['file_count'] = 0
if 'download_ready' not in st.session_state:
    st.session_state['download_ready'] = False

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
    if st.button("🗑️ 처음으로 (메모리 정리)"):
        # 강력한 초기화
        try:
            shutil.rmtree(st.session_state['storage_path'])
        except: pass
        st.session_state['storage_path'] = tempfile.mkdtemp()
        st.session_state['file_count'] = 0
        st.session_state['download_ready'] = False
        gc.collect() # 메모리 청소
        st.rerun()

# --- 메인 로직 ---
if st.session_state['download_ready']:
    st.success(f"🎉 작업 성공! 총 {st.session_state['file_count']}장")
    
    zip_path = os.path.join(st.session_state['storage_path'], "Result.zip")
    
    if os.path.exists(zip_path):
        # 파일 크기 확인
        file_size = os.path.getsize(zip_path) / (1024 * 1024)
        st.caption(f"파일 크기: {file_size:.2f} MB")
        
        with open(zip_path, "rb") as f:
            st.download_button(
                label="📥 결과물 다운로드 (클릭)",
                data=f,
                file_name="CAMPSMAP_Result.zip",
                mime="application/zip",
                type="primary"
            )
    else:
        st.error("파일이 사라졌습니다. 초기화 후 다시 시도하세요.")
        
    st.warning("⚠️ 다음 작업을 하려면 사이드바의 '처음으로'를 눌러 메모리를 비워주세요.")

else:
    if not loaded_filters:
        st.error("⚠️ 필터 파일 없음")
    else:
        uploaded_files = st.file_uploader("사진 선택 (너무 많이 올리면 렉걸릴 수 있음)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

        if uploaded_files:
            if st.button(f"🚀 {len(uploaded_files)}장 변환 시작 (안전 모드)"):
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                processed_now = 0
                
                # 1. 변환 루프
                for idx, uploaded_file in enumerate(uploaded_files):
                    status_text.text(f"처리 중... ({idx+1}/{len(uploaded_files)})")
                    try:
                        # 이미지 열기
                        img = Image.open(uploaded_file).convert('RGB')
                        img = ImageOps.exif_transpose(img)
                        
                        # [핵심] 리사이징: 1280px로 제한 (메모리 절약의 핵심)
                        img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                        
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
                        
                        # 필터 적용 및 저장
                        fname_prefix = os.path.splitext(uploaded_file.name)[0]
                        for fname, lut in loaded_filters.items():
                            try:
                                save_path = os.path.join(st.session_state['storage_path'], f"{fname_prefix}_{fname}.jpg")
                                # [핵심] quality=85 (용량 줄이기)
                                base_img.point(lut).save(save_path, quality=85, subsampling=0)
                                processed_now += 1
                            except: pass
                            
                    except Exception as e:
                        print(f"Error: {e}")
                        pass
                    
                    # [핵심] 한 장 처리할 때마다 메모리 청소 및 이미지 객체 삭제
                    del img
                    del img_arr
                    del base_img
                    gc.collect()
                    
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                
                st.session_state['file_count'] += processed_now
                
                # 2. ZIP 생성 (여기서 뻗지 않도록 주의)
                status_text.text("파일 압축 중... (조금만 기다려주세요)")
                zip_path = os.path.join(st.session_state['storage_path'], "Result.zip")
                
                try:
                    # 다시 압축(Deflated)을 사용하되, 메모리 사용량을 줄임
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(st.session_state['storage_path']):
                            for file in files:
                                if file == "Result.zip": continue
                                file_path = os.path.join(root, file)
                                zipf.write(file_path, arcname=file)
                except Exception as e:
                    st.error(f"압축 중 오류 발생: {e}")
                    st.stop()

                # 3. 완료 상태로 전환
                st.session_state['download_ready'] = True
                st.rerun()
