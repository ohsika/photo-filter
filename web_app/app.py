import streamlit as st
from PIL import Image, ImageOps, ImageFilter
import numpy as np
import os
import io
import zipfile

# --- 페이지 설정 ---
st.set_page_config(page_title="CAMPSMAP Darkroom", page_icon="📸", layout="wide")

# --- CSS 스타일링 (체크박스 강조 등) ---
st.markdown("""
<style>
    div[data-testid="stImage"] {
        border-radius: 10px;
        overflow: hidden;
    }
    .stButton>button {
        border-radius: 8px;
    }
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
                
                lut = []
                for i in range(4, 7):
                    line_data = [int(x) for x in lines[i].replace(',', ' ').split() if x.strip().isdigit()]
                    lut.extend(line_data)
                
                if len(lut) < 768: lut += [lut[-1]] * (768 - len(lut))
                else: lut = lut[:768]
                filters[f_name] = lut
        except: pass
    return filters

# --- 이미지 처리 함수 ---
def process_base_image(image_bytes, rotation=0, width=None):
    """이미지 로드 -> 회전 -> 리사이징 -> 베이스 효과"""
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img) # EXIF 회전 정보 반영
    
    # [기능 추가] 사용자 강제 회전 (90도 단위)
    if rotation != 0:
        img = img.rotate(-rotation, expand=True)
    
    # 미리보기용 리사이징
    if width:
        w_percent = (width / float(img.size[0]))
        h_size = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((width, h_size), Image.Resampling.LANCZOS)
    
    # 베이스 효과 (블러+비네팅+그레인)
    base = img.filter(ImageFilter.GaussianBlur(0.3))
    
    w, h = base.size
    x, y = np.meshgrid(np.linspace(-1, 1, w), np.linspace(-1, 1, h))
    mask = 1 - np.clip(np.sqrt(x**2 + y**2) - 0.5, 0, 1) * 0.4
    mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)
    
    arr = np.array(base.convert('RGB'), dtype=np.float32) * mask
    noise = np.random.normal(0, 12, (h, w))
    noise = np.repeat(noise[:, :, np.newaxis], 3, axis=2)
    final = np.clip(arr + noise, 0, 255).astype(np.uint8)
    
    return Image.fromarray(final)

def apply_lut(image, lut):
    return image.convert('RGB').point(lut)

# --- 세션 초기화 ---
if 'processed_images' not in st.session_state:
    st.session_state.processed_images = []
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'rotation_angle' not in st.session_state:
    st.session_state.rotation_angle = 0
if 'upload_key' not in st.session_state:
    st.session_state.upload_key = 0

# --- 메인 화면 ---
st.title("🎞️ CAMPSMAP Darkroom")
st.markdown("사진을 한 장씩 확인하며 **원하는 필터 버전을 여러 개 선택**하세요.")

loaded_filters = load_filters()
if not loaded_filters:
    st.error("⚠️ 필터 파일이 없습니다.")
    st.stop()

# 1. 업로드
uploaded_files = st.file_uploader(
    "현상할 사진을 모두 선택하세요", 
    type=['jpg', 'jpeg', 'png'], 
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.upload_key}"
)

# 파일 리스트가 바뀌면 초기화
if not uploaded_files:
    st.session_state.current_index = 0
    st.session_state.processed_images = []
    st.session_state.rotation_angle = 0

# 2. 편집 프로세스
if uploaded_files:
    total_files = len(uploaded_files)
    
    # (A) 모든 작업 완료 시 -> 다운로드
    if st.session_state.current_index >= total_files:
        st.success(f"🎉 총 {len(st.session_state.processed_images)}장의 사진 현상이 완료되었습니다!")
        st.balloons()
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for fname, img_bytes in st.session_state.processed_images:
                zip_file.writestr(fname, img_bytes)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📦 결과물 ZIP 다운로드", 
                data=zip_buffer.getvalue(), 
                file_name="CAMPSMAP_Results.zip", 
                mime="application/zip", 
                use_container_width=True,
                type="primary"
            )
        with col2:
            if st.button("🔄 처음부터 다시 하기", use_container_width=True):
                st.session_state.upload_key += 1
                st.rerun()

    # (B) 개별 사진 편집 화면
    else:
        current_file = uploaded_files[st.session_state.current_index]
        file_bytes = current_file.getvalue()
        
        # 상단 컨트롤 바 (진행률 + 회전 버튼)
        st.progress((st.session_state.current_index) / total_files)
        
        col_info, col_rot = st.columns([3, 1])
        with col_info:
            st.markdown(f"### 🖼️ [{st.session_state.current_index + 1} / {total_files}] : {current_file.name}")
        with col_rot:
            if st.button("🔄 90° 회전"):
                st.session_state.rotation_angle = (st.session_state.rotation_angle + 90) % 360
                st.rerun()

        # 미리보기 생성 (현재 회전각도 반영)
        preview_img = process_base_image(file_bytes, rotation=st.session_state.rotation_angle, width=300)
        
        # 필터 선택 그리드 (Form으로 묶어서 한 번에 제출)
        with st.form(key=f"form_{st.session_state.current_index}"):
            st.caption("마음에 드는 버전을 **모두 체크(v)** 하세요.")
            
            filter_names = sorted(list(loaded_filters.keys()))
            cols = st.columns(4) # 4열 그리드
            
            # 선택된 필터를 담을 딕셔너리
            selections = {}
            
            for idx, f_name in enumerate(filter_names):
                with cols[idx % 4]:
                    # 1. 필터 적용된 썸네일 보여주기
                    filtered_thumb = apply_lut(preview_img, loaded_filters[f_name])
                    st.image(filtered_thumb, use_container_width=True)
                    
                    # 2. 설명과 체크박스
                    desc = FILTER_DESCRIPTIONS.get(f_name, "")
                    label = f"**{f_name}**"
                    if desc: label += f"\n:gray[{desc}]"
                    
                    # 체크박스 (key를 유니크하게 해서 상태 꼬임 방지)
                    checked = st.checkbox(label, key=f"chk_{st.session_state.current_index}_{f_name}")
                    selections[f_name] = checked
            
            st.divider()
            
            # 하단 네비게이션
            # Form Submit 버튼
            col_next, col_skip = st.columns([2, 1])
            with col_next:
                submit = st.form_submit_button("✅ 선택 완료 / 다음 사진으로 (Next)", type="primary", use_container_width=True)
            with col_skip:
                skip = st.form_submit_button("⏩ 건너뛰기 (Skip)", use_container_width=True)

        # 제출 버튼 눌렀을 때 처리 로직
        if submit:
            selected_filters = [k for k, v in selections.items() if v]
            
            if not selected_filters:
                st.warning("선택된 필터가 없습니다. 마음에 드는 게 없다면 '건너뛰기'를 눌러주세요.")
            else:
                # 고화질 변환 (한 번만 로드해서 효율적으로 처리)
                full_base = process_base_image(file_bytes, rotation=st.session_state.rotation_angle, width=2000)
                fname_no_ext = os.path.splitext(current_file.name)[0]
                
                with st.spinner("저장 중..."):
                    for f_name in selected_filters:
                        final = apply_lut(full_base, loaded_filters[f_name])
                        
                        # 메모리 저장
                        img_io = io.BytesIO()
                        final.save(img_io, format='JPEG', quality=95, subsampling=0)
                        
                        save_name = f"{fname_no_ext}_{f_name}.jpg"
                        st.session_state.processed_images.append((save_name, img_io.getvalue()))
                
                # 다음 단계로
                st.session_state.rotation_angle = 0 # 회전 초기화
                st.session_state.current_index += 1
                st.rerun()

        if skip:
            st.session_state.rotation_angle = 0
            st.session_state.current_index += 1
            st.rerun()
