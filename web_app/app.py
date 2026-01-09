import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import io
import zipfile

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Selector", page_icon="📸", layout="wide")

# --- 스타일링 (버튼 및 그리드 간격 조정) ---
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
    }
    div.row-widget.stRadio > div{flex-direction:row;}
</style>
""", unsafe_allow_html=True)

# --- 필터 설명 데이터 ---
FILTER_DESCRIPTIONS = {
    "Classic": "표준 필름", "Vintage": "따뜻한 빈티지", "Mono": "부드러운 흑백",
    "Kino": "영화 색감", "Kodaclone": "코닥 스타일", "101Clone": "도시적 감성",
    "Art-Club": "몽환적 보라", "Boom-Boom": "강렬한 채도", "Bubblegum": "핑크 파스텔",
    "Cross-Pross": "청록색 틴트", "Eternia": "물 빠진 감성", "Grunge": "거친 락시크",
    "Midas": "황금빛 노을", "Narnia": "겨울 판타지", "Pastel": "순한 봄",
    "Pistachio": "싱그러운 녹색", "Temporum": "세피아 추억", "Uddh": "대지의 색",
    "X-Pro": "강한 대비", "Black_And_White": "강한 흑백", "Bleach": "묵직한 톤"
}

# --- 필터 로딩 ---
@st.cache_data
def load_filters():
    filters = {}
    # 현재 파일 위치 기준 탐색
    current_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [
        os.path.join(current_dir, "Filters"),
        os.path.join(current_dir, "web_app", "Filters"),
        "Filters"
    ]
    
    for filter_dir in possible_paths:
        if not os.path.exists(filter_dir): continue
        try:
            files = [f for f in os.listdir(filter_dir) if f.lower().endswith(('.fit', '.flt'))]
            for fname in files:
                f_name = os.path.splitext(fname)[0]
                if f_name in filters: continue
                
                with open(os.path.join(filter_dir, fname), 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                if len(lines) < 7: continue
                
                # 데이터 파싱
                lut = []
                for i in range(4, 7):
                    line_data = [int(x) for x in lines[i].replace(',', ' ').split() if x.strip().isdigit()]
                    lut.extend(line_data)
                
                # 768개 보정
                if len(lut) < 768: lut += [lut[-1]] * (768 - len(lut))
                else: lut = lut[:768]
                
                filters[f_name] = lut
        except: pass
    return filters

# --- 이미지 처리 (캐싱으로 속도 향상) ---
@st.cache_data
def apply_base_effects(image_bytes, width=None):
    """베이스 효과(그레인, 비네팅)만 적용된 이미지 반환"""
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    
    # 미리보기용 리사이징 (속도 핵심)
    if width:
        w_percent = (width / float(img.size[0]))
        h_size = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((width, h_size), Image.Resampling.LANCZOS)
    
    # 효과 적용
    base = img.filter(ImageFilter.GaussianBlur(0.3))
    
    # 비네팅
    w, h = base.size
    x, y = np.meshgrid(np.linspace(-1, 1, w), np.linspace(-1, 1, h))
    mask = 1 - np.clip(np.sqrt(x**2 + y**2) - 0.5, 0, 1) * 0.4
    mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    arr = np.array(base.convert('RGB'), dtype=np.float32) * mask
    
    # 그레인
    noise = np.random.normal(0, 12, (h, w))
    noise = np.repeat(noise[:, :, np.newaxis], 3, axis=2)
    final = np.clip(arr + noise, 0, 255).astype(np.uint8)
    
    return Image.fromarray(final)

def apply_lut(image, lut):
    """LUT 적용"""
    return image.convert('RGB').point(lut)

# --- 세션 상태 관리 (진행 상황 저장) ---
if 'processed_images' not in st.session_state:
    st.session_state.processed_images = [] # 최종 결과물 저장소
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'upload_key' not in st.session_state:
    st.session_state.upload_key = 0

# --- 메인 로직 ---
st.title("📸 CAMPSMAP : Pick Your Best")
st.markdown("모든 필터를 미리보고, **가장 마음에 드는 사진을 한 장씩 선택**하세요.")

loaded_filters = load_filters()

if not loaded_filters:
    st.error("⚠️ 필터 파일이 없습니다. GitHub에 Filters 폴더를 확인해주세요.")
    st.stop()

# 1. 파일 업로드 단계
uploaded_files = st.file_uploader(
    "사진들을 업로드하세요 (여러 장 가능)", 
    type=['jpg', 'jpeg', 'png'], 
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.upload_key}"
)

# 업로드가 새로 되면 인덱스 초기화
if uploaded_files and len(uploaded_files) > 0:
    # 세션에 파일이 저장된 상태인지 확인 (새로고침 방지용 단순 체크)
    pass
else:
    # 파일이 없으면 초기화
    st.session_state.current_index = 0
    st.session_state.processed_images = []

# 2. 작업 진행 단계
if uploaded_files:
    total_files = len(uploaded_files)
    
    # (A) 모든 작업이 끝났을 때 -> 다운로드 화면
    if st.session_state.current_index >= total_files:
        st.success("🎉 모든 사진 선택이 완료되었습니다!")
        st.balloons()
        
        # ZIP 생성
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for fname, img_bytes in st.session_state.processed_images:
                zip_file.writestr(fname, img_bytes)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📦 결과물 ZIP 다운로드",
                data=zip_buffer.getvalue(),
                file_name="CAMPSMAP_Selected.zip",
                mime="application/zip",
                use_container_width=True
            )
        with col2:
            if st.button("🔄 처음부터 다시 하기", use_container_width=True):
                st.session_state.current_index = 0
                st.session_state.processed_images = []
                st.session_state.upload_key += 1
                st.rerun()

    # (B) 작업 중일 때 -> 선택 화면 (Grid)
    else:
        # 현재 처리할 파일 가져오기
        current_file = uploaded_files[st.session_state.current_index]
        file_bytes = current_file.getvalue()
        
        # 상단 진행바
        progress = (st.session_state.current_index) / total_files
        st.progress(progress)
        st.markdown(f"### 🖼️ [{st.session_state.current_index + 1} / {total_files}] : {current_file.name}")
        st.caption("아래 미리보기 중에서 가장 마음에 드는 사진의 **[선택]** 버튼을 누르세요.")

        # --- 미리보기 이미지 생성 (빠르게) ---
        # 1. 베이스 효과 적용된 썸네일 (너비 300px로 제한하여 속도 확보)
        preview_base = apply_base_effects(file_bytes, width=300)
        
        # 필터 이름 정렬
        filter_names = sorted(list(loaded_filters.keys()))
        
        # --- 그리드 레이아웃 (3열) ---
        cols = st.columns(3) # 4열을 원하면 st.columns(4)로 변경
        
        for idx, f_name in enumerate(filter_names):
            # 현재 컬럼 위치 계산
            col = cols[idx % 3]
            
            with col:
                # 필터 적용
                filtered_thumb = apply_lut(preview_base, loaded_filters[f_name])
                
                # 이미지 표시
                st.image(filtered_thumb, use_container_width=True)
                
                # 설명 표시
                desc = FILTER_DESCRIPTIONS.get(f_name, f_name)
                st.markdown(f"**{f_name}**")
                
                # [선택] 버튼
                # 버튼을 누르면 -> 고화질 변환 -> 저장 -> 인덱스 증가 -> 리런
                if st.button(f"👉 선택 ({desc})", key=f"btn_{st.session_state.current_index}_{f_name}"):
                    
                    # 1. 고화질(Full-Size)로 다시 변환
                    # (웹 속도를 위해 2000px 정도가 적당, 원본 유지는 width=None)
                    full_base = apply_base_effects(file_bytes, width=2000)
                    final_img = apply_lut(full_base, loaded_filters[f_name])
                    
                    # 2. 메모리에 저장
                    img_io = io.BytesIO()
                    final_img.save(img_io, format='JPEG', quality=95, subsampling=0)
                    
                    # 파일명 결정 (원본이름_필터명.jpg)
                    fname_no_ext = os.path.splitext(current_file.name)[0]
                    save_name = f"{fname_no_ext}_{f_name}.jpg"
                    
                    st.session_state.processed_images.append((save_name, img_io.getvalue()))
                    
                    # 3. 다음 장으로 넘어가기
                    st.session_state.current_index += 1
                    st.rerun()

        st.divider()
        st.caption("Tip: 사진이 많으면 미리보기 생성에 약간의 시간이 걸릴 수 있습니다.")
