import streamlit as st

def style_sidebar():
    return st.markdown("""
    <style>
    /* 사이드바 전체 여백 제거 */
    section[data-testid="stSidebar"] {
        padding: 0px !important; /* 가로 여백 */ 
        margin: 0px !important; /* 사이드바 자체 위치 */ 
    }

    /* 사이드바 내부 요소 각각에 대한 여백 제거 */
    section[data-testid="stSidebar"] [data-testid="stElementContainer"] {
        padding: 0px !important; /* 사이드바 내부 요소 간 가로 여백 */
        margin-top: -6px !important; /* 사이드바 내부 요소 간 세로 여백 */
        margin-bottom: -6px !important; /* 사이드바 내부 요소 간 세로 여백 */
    }

    /* 필요시 제목 요소 여백도 줄이기 */
    section[data-testid="stSidebar"] [data-testid="stHeading"] {
        margin-top: 2px !important; /* 제목 요소 가로세로 여백*/
        margin-bottom: -2px !important; /* 제목 요소 가로세로 여백*/
    }
    </style>
    """, unsafe_allow_html=True)

def style_message():
    return st.markdown("""
    <style>
    div[class*="stChatMessage st-emotion-cache"] h2 {
        font-size: 1.4rem !important; /* # 레벨 마크다운 글자 크기 및 여백 조정 */
        padding-top: 0.3rem !important;
        padding-bottom: 0.2rem !important;
    }
    div[class*="stChatMessage st-emotion-cache"] div[data-testid="stMarkdownPre"]:has(div[data-testid="stCode"]) { 
        margin-bottom: 0.2rem !important; /* 코드블록 위쪽과 일반 메세지 간 간격 */
        margin-top: -0.8rem !important; /* 코드블록 아래쪽과 일반 메세지 간 간격(-1로 설정해야 실제 간격 0) */
    }
    div[class*="stChatMessage st-emotion-cache"] div[data-testid="stCode"] pre {
        padding: 0.3rem 2.4rem 0.3rem 0.3rem !important; /* 코드블록 안쪽과 실제 코드 글자 사이 간의 간격 */
    }
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {
        background-color: rgba(230, 228, 220, 0.5) !important; /* 사용자 메세지 백그라운드 색 설정*/
    }
    div[data-testid="stChatMessageAvatarUser"] {
        background-color: rgb(16, 61, 51) !important; /* 사용자 아바타 색상 설정*/
        border-radius: 1rem; /* 사용자 아바타 가장자리 모양 설정*/
    }
    div[data-testid="stChatMessageAvatarAssistant"] {
        display: none !important; /* 어시스턴트 아바타 숨기기*/
    }
    div[data-testid="stCode"] {
        border: 1px solid #DEDCD5 !important; /* 코드블록 색상 및 형태*/
        border-radius: 8px !important;
        background: rgb(250, 250, 250) !important; 
        background-color: rgb(250, 250, 250) !important; 
    }
    </style>
    """, unsafe_allow_html=True)

def style_buttons():
    return st.markdown("""
    <style>
    /* 모든 버튼 기본 스타일 (배경색, 테두리, 색상 통일) */
    button[data-testid="stBaseButton-secondary"] {
        background-color: #F0EEE6 !important;
        color: black !important;
        border: 1px solid #DEDCD5 !important;
        padding: 0.3em 0.8em !important;
        border-radius: 4px !important;
        transition: background-color 0.3s ease;
        display: flex;
        align-items: center;
        justify-content: center;  /* 기본은 가운데 정렬 */
        width: 100%;
    }
    
    /* 호버 스타일 */
    button[data-testid="stBaseButton-secondary"]:hover {
        background-color: #DEDCD5 !important;
        color: black !important;
        border: 1px solid #DEDCD5 !important;
    }
    
    /* 🔸 리스트 버튼만 왼쪽 정렬: session 키 포함한 버튼 컨테이너 내부 */
    div[class*="st-key-session_"] button[data-testid="stBaseButton-secondary"] {
        justify-content: flex-start !important;
        padding-left: 0.4em !important;
    }
    
    /* 🔸 JSON 버튼의 텍스트 중앙 정렬 보장 (오버라이드용) */
    div.stDownloadButton button[data-testid="stBaseButton-secondary"] {
        justify-content: center !important;
    }
    
    /* 🔸 로그아웃, 대화초기화 등 기본 버튼들도 중앙 정렬 */
    div.stElementContainer.st-key-logout_btn button[data-testid="stBaseButton-secondary"],
    div.stElementContainer:not([class*="st-key-session_"]) button[data-testid="stBaseButton-secondary"]:has(p:contains("대화 초기화")) {
        justify-content: center !important;
    }
    </style>
    """, unsafe_allow_html=True)

def style_highlighting():
    #임시로 엘리먼트 하이라이팅
    return st.markdown("""
    <style>
    div[data-testid="stElementContainer"] {
        outline: 1px dashed red !important;
        /* background: rgb(250, 0, 0) !important; */
        /* background-color: rgb(250, 0, 0) !important;*/
    }
    div[data-testid="stCode"] {
        outline: 1px solid blue !important;
        /* background: rgb(0, 0, 250) !important; */
        /* background-color: rgb(0, 0, 250) !important;*/
        
    }
    </style>
    """, unsafe_allow_html=True)

