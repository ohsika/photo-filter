import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import shutil
import tempfile
import gc

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Debug Mode", page_icon="🛠️")

st.title("🛠️ CAMPSMAP (안전 모드)")
st.markdown("현재 **작동 상태를 실시간으로 표시**합니다.")

# --- 세션 초기화 ---
if 'storage_path' not in st.session_state:
    st.session_state['storage_path'] = tempfile.mkdtemp()
    st.session_state['file_count'] = 0

# --- 필터 로딩 (디버깅 메시지 추가) ---
@st.cache_data
def load_filters():
    filters = {}
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 찾을 경로들
    possible_paths = [
        os.path.join(current_dir, "Filters"),
        os.path.join(current_dir, "web_app", "Filters"),
        "Filters"
    ]
    
    found_path = "못 찾음"
    
    for filter_dir in possible_paths:
        if os.path.exists(filter_dir):
            found_path = filter_dir
            try:
                files = [f for f in os.listdir(filter_dir) if f.lower().endswith(('.fit', '.flt'))]
                for fname in files:
                    full_path = os.path.join(filter_dir, fname)
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    if len(lines) < 7: continue
                    
                    # 파싱
                    def parse_line(line_str):
                        return [int(x) for x in line_str.replace(',', ' ').split() if x.strip().isdigit()]
                    
                    r = parse_line(lines[4])
                    g = parse_line(lines[5])
                    b = parse_line(lines[6])
                    full_lut = r + g + b
                    
                    if len(full_lut) < 768: full_lut += [full_lut[-1]] * (768 - len(full_lut))
                    else: full_lut = full_lut[:768]
                    
                    filters[os.path.splitext(fname)[0]] = full_lut
            except:
                continue
    
    return filters, found_path

# --- 로딩 상태 확인 ---
loaded_filters, path_used = load_filters()

st.divider()
st.subheader("1. 상태 점검")
st.write(f"📂 필터 폴더 위치: `{path_used}`")
if not loaded_filters:
    st.error("❌ 로드된 필터가 0개입니다! 이러면 변환이 안 됩니다.")
    st.info("GitHub에 Filters 폴더 안에 파일이 들어있는지 확인하세요.")
else:
    st.success(f"✅ 필터 {len(loaded_filters)}개 로드 완료! (정상)")

# --- 사이드바 ---
with st.sidebar:
    st.header(f"보관함: {st.session_state['file_count']}장")
    if st.session_state['file_count'] > 0:
        shutil.make_archive(st.session_state['storage_path'], 'zip', st.session_state['storage_path'])
        with open(st.session_state['storage_path'] + ".zip", "rb") as f:
            st.download_button("📥 ZIP 다운로드", f, "Result.zip", "application/zip")
        
        if st.button("🗑️ 초기화"):
            shutil.rmtree(st.session_state['storage_path'])
            os.makedirs(st.session_state['storage_path'])
            st.session_state['file_count'] = 0
            st.rerun()

# --- 메인 업로더 ---
st.divider()
st.subheader("2. 사진 업로드")
uploaded_files = st.file_uploader("사진 선택", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

if uploaded_files:
    # 버튼을 누르면 즉시 메시지를 띄움
    if st.button(f"🚀 {len(uploaded_files)}장 변환 시작"):
        
        if not loaded_filters:
            st.error("필터가 없어서 작업을 시작할 수 없습니다.")
            st.stop()

        status_box = st.container()
        progress_bar = status_box.progress(0)
        log_text = status_box.empty()
        
        log_text.write("⏳ 작업 시작... (멈춘 거 아님)")
        
        processed_count = 0
        
        for idx, uploaded_file in enumerate(uploaded_files):
            log_text.write(f"processing: {uploaded_file.name}...")
            
            try:
                img = Image.open(uploaded_file).convert('RGB')
                img = ImageOps.exif_transpose(img)
                
                # [안전 모드] 해상도 1500px로 제한 (서버 다운 방지)
                img.thumbnail((1500, 1500), Image.Resampling.LANCZOS)
                
                img_arr = np.array(img, dtype=np.float32)
                
                # 효과 적용 (Grain + Vignette)
                h, w, c = img_arr.shape
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
                        base_img.point(lut).save(save_path, quality=90, subsampling=0)
                        processed_count += 1
                    except: pass
                    
            except Exception as e:
                st.error(f"에러 ({uploaded_file.name}): {e}")
            
            gc.collect()
            progress_bar.progress((idx + 1) / len(uploaded_files))
        
        st.session_state['file_count'] += processed_count
        
        # [중요] st.rerun()을 제거했습니다. 이제 결과 메시지가 보일 겁니다.
        st.success(f"🎉 작업 끝! 총 {processed_count}장이 생성되었습니다.")
        st.info("👈 왼쪽 사이드바에서 'ZIP 다운로드' 버튼을 누르세요.")
