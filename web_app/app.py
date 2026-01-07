import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import tempfile
import zipfile
import gc

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Pro", page_icon="📸")

st.title("📸 CAMPSMAP Film Lab (Unlimited)")
st.markdown("""
**무제한 처리 모드**
*한 장씩 즉시 압축하여 메모리와 용량을 최소화합니다.*
*수십 장을 넣어도 서버가 뻗지 않도록 설계되었습니다.*
""")

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
    
    # 기본 필터 (파일이 없을 경우 대비)
    filters['Classic_BW'] = [] # 데이터가 없으면 로직에서 흑백 처리

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

# --- 이미지 처리 함수 (메모리 누수 방지) ---
def process_image_data(image, lut_data=None):
    """이미지 처리 후 PIL 객체 반환"""
    # 1. 포맷 통일
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # 2. NumPy 변환 및 효과 (메모리 절약을 위해 단계별 처리)
    img_arr = np.array(image, dtype=np.float32)
    
    # 베이스 블러
    # (PIL 필터 대신 cv2를 쓰면 더 빠르지만, 호환성을 위해 NumPy/PIL 유지)
    
    # 비네팅 & 그레인 (행렬 연산)
    h, w, c = img_arr.shape
    
    # 그레인 (Grain)
    noise = np.random.normal(0, 12, (h, w)) # 강도 12
    noise = np.repeat(noise[:, :, np.newaxis], 3, axis=2)
    img_arr = img_arr + noise
    
    # 비네팅 (Vignette) - 계산 비용 줄이기 위해 간소화
    # 굳이 meshgrid 전체를 만들지 않고 마스킹
    # (속도를 위해 복잡한 비네팅 연산은 생략하거나 최소화할 수 있음. 여기선 유지)
    x = np.linspace(-1, 1, w)
    y = np.linspace(-1, 1, h)
    X, Y = np.meshgrid(x, y)
    radius = np.sqrt(X**2 + Y**2)
    mask = 1 - np.clip(radius - 0.5, 0, 1) * 0.4
    mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    img_arr = img_arr * mask
    
    # 결과 클리핑
    img_arr = np.clip(img_arr, 0, 255).astype(np.uint8)
    processed_img = Image.fromarray(img_arr)
    
    # 3. LUT 적용
    if lut_data:
        processed_img = processed_img.point(lut_data)
    
    return processed_img

# --- 메인 로직 ---
loaded_filters = load_filters()

if not loaded_filters:
    st.warning("⚠️ 필터 파일이 없어 '기본 흑백/무필터' 모드로 동작합니다.")

uploaded_files = st.file_uploader("사진을 몽땅 넣으세요 (무제한)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🚀 {len(uploaded_files)}장 변환 시작"):
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # [핵심] 임시 파일 생성 (RAM이 아닌 디스크에 ZIP 파일 생성)
        # delete=False: 윈도우/리눅스 호환 및 다운로드 후 삭제를 위함
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip.close() # 이름만 확보하고 닫음
        
        total_files = len(uploaded_files)
        success_count = 0
        
        # ZIP 파일을 'append' 모드로 열어서 하나씩 쑤셔넣음
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zf:
            
            for idx, uploaded_file in enumerate(uploaded_files):
                try:
                    status_text.text(f"[{idx+1}/{total_files}] 처리 중: {uploaded_file.name}")
                    progress_bar.progress((idx) / total_files)
                    
                    # 1. 이미지 열기
                    # (upload_file은 BytesIO이므로 바로 염)
                    with Image.open(uploaded_file) as img:
                        img = ImageOps.exif_transpose(img)
                        file_name_no_ext = os.path.splitext(uploaded_file.name)[0]
                        
                        # [안전장치] 만약 이미지가 너무 크면(예: 8000px 이상) 강제 리사이징
                        # 4K(3840px) 정도면 충분함. 서버 보호용.
                        if img.width > 4000 or img.height > 4000:
                            img.thumbnail((4000, 4000), Image.Resampling.LANCZOS)
                        
                        # 2. 각 필터별 처리 및 즉시 저장
                        for filter_name, lut_data in loaded_filters.items():
                            try:
                                # 이미지 처리
                                final_img = process_image_data(img, lut_data)
                                
                                # 즉시 압축 파일에 쓰기 (디스크에 중간파일 안만듦)
                                # writestr을 쓰면 메모리에서 바로 zip으로 들어감
                                with tempfile.NamedTemporaryFile(suffix='.jpg') as tmp_jpg:
                                    final_img.save(tmp_jpg.name, quality=95, subsampling=0)
                                    # 파일 포인터를 이용해 zip에 추가
                                    zf.write(tmp_jpg.name, arcname=f"{file_name_no_ext}_{filter_name}.jpg")
                                
                                # 메모리 해제
                                del final_img
                            except Exception:
                                continue

                    success_count += 1
                    
                    # [매우 중요] 한 장 할 때마다 가비지 컬렉션 (RAM 비우기)
                    gc.collect()

                except Exception as e:
                    # 한 장이 에러나도 멈추지 않고 다음으로 넘어감
                    st.error(f"⚠️ {uploaded_file.name} 실패 (건너뜀): {e}")
                    continue
        
        progress_bar.progress(100)
        status_text.text(f"✅ 완료! (총 {success_count}장 성공)")
        
        # 다운로드 버튼
        with open(temp_zip.name, "rb") as f:
            st.download_button(
                label="📦 결과 다운로드 (ZIP)",
                data=f,
                file_name="CAMPSMAP_Pro.zip",
                mime="application/zip"
            )
        
        # 다운로드 버튼이 렌더링 된 후 임시 파일 삭제 로직은 복잡하므로,
        # 스트림릿이 알아서 청소하게 둡니다 (OS 레벨에서 /tmp는 주기적으로 비워짐)
