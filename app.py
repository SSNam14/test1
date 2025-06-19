import streamlit as st
import uuid
import streamlit.components.v1 as components
import extra_streamlit_components as stx

import time

st.set_page_config(page_title="Claude", page_icon="🤖")
st.title("Claude")

import chat, auth, styles, text_code_parser, history

max_input_token = chat.max_input_token
COOKIE_KEY = 'user_login'

styles.style_sidebar()
styles.style_buttons()
styles.style_message()
styles.style_navigation()

db = history.initialize_firebase()

cookie_manager = stx.CookieManager() #main함수에서 정의되어야 함
auth.initialize_cookie(cookie_manager, COOKIE_KEY)
    
if 'session_id' not in st.session_state:
    url_session_id = st.query_params.get('session_id', None)
    
    if url_session_id:
        # URL에 session_id가 있으면 사용
        st.session_state.session_id = url_session_id
        print(f"Using session_id from URL: {url_session_id}")
        st.session_state.messages = history.load_conversation_from_db(url_session_id, db)
    else:
        # URL에 없으면 새로 생성하고 URL에 설정
        new_session_id = str(uuid.uuid4())
        st.session_state.session_id = new_session_id
        st.query_params['session_id'] = new_session_id
        print(f"Generated new session_id: {new_session_id}")

# 세션 ID 관리 (추가)
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
print("현재 대화의 session id:", st.session_state.session_id)

# 세션 상태 초기화
if 'messages' not in st.session_state:
    st.session_state.messages = []

# 로그인 상태 관리
if 'user_email' not in st.session_state:
    st.session_state.user_email = None

if 'user_name' not in st.session_state:
    st.session_state.user_name = None

if 'num_input_tokens' not in st.session_state:
    st.session_state.num_input_tokens = 0

# 편집 관련 상태 변수 초기화
if 'editing_message' not in st.session_state:
    st.session_state.editing_message = None

# 새 응답 생성 중 상태 추적
if 'generating_response' not in st.session_state:
    st.session_state.generating_response = False
    
# 새 메시지 추가 확인 플래그
if 'new_message_added' not in st.session_state:
    st.session_state.new_message_added = False
    
# 응답 전 응답 관련 설정
with st.sidebar:
    if st.button(":material/edit_square: 새 채팅", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.num_input_tokens = 0
        st.rerun()
        
    st.header(":material/account_circle: 사용자 로그인")
    
    if st.session_state.user_email: # 로그인된 상태
        st.markdown(f'안녕하세요, {st.session_state.user_name}님!</p>', unsafe_allow_html=True)
        if st.button(":material/logout: 로그아웃", key="logout_btn", use_container_width=True):
            auth.logout(cookie_manager, COOKIE_KEY)
                
    else: # 로그인되지 않은 상태
        st.text_input("이메일 주소", key="email_input", placeholder='abcd@gmail.com', label_visibility='collapsed')
        
        if st.button(":material/login: 로그인", key="login_btn", use_container_width=True, help="로그인하시면 대화 기록이 저장됩니다."):
            auth.login(db, cookie_manager, COOKIE_KEY)
            st.rerun()  # 로그인 후 즉시 페이지 새로고침

        if 'login_error' in st.session_state and st.session_state.login_error:
            st.error(st.session_state.error_message)
    
    
    st.header(":material/settings:  응답 설정")
    model = st.selectbox(
        "모델 선택",
        ["claude-sonnet-4-20250514", "claude-3-7-sonnet-20250219", "claude-opus-4-20250514", "claude-3-opus-20240229", ]
    )
    
    temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.7, step=0.1, 
                            help="값이 높을수록 창의적이고 다양한 답변, 낮을수록 일관되고 예측 가능한 답변")

    system_prompt = st.text_area("시스템 프롬프트", "간결하게", help="AI의 역할과 응답 스타일을 설정합니다")


# 메시지 편집 함수
def edit_message(message_index):
    st.session_state.editing_message = message_index

# 메시지 편집 제출 함수
def submit_edit(message_index, new_content):
    # 기존 메시지 내용 업데이트
    st.session_state.messages[message_index]["content"] = new_content
    st.session_state.messages = st.session_state.messages[:message_index + 1]     # 이 메시지 이후의 모든 메시지 삭제
    st.session_state.editing_message = None
    st.session_state.generating_response = True
    history.save_conversation_to_db(db)
    st.rerun()


#채팅 네비게이션 설정
nav_buttons = ""
n_user_messages = 0
for message in st.session_state.messages:
    if message["role"] == "user":
        nav_buttons += f'<a href="#msg-{n_user_messages}" class="nav-button">{n_user_messages+1}</a>'
        n_user_messages += 1

st.markdown(f"""
<div class="fixed-nav">
    {nav_buttons}
</div>
""", unsafe_allow_html=True)

#기존 메세지 표시 
n_user_messages = 0
for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "user": #유저 메세지-채팅 네비게이션, 편집 기능 
            st.markdown(f'<div id="msg-{n_user_messages}" style="scroll-margin-top: 70px;"></div>',  unsafe_allow_html=True)
            n_user_messages+=1

            # 편집 중인 메시지
            if st.session_state.editing_message == i:
                height = min(680, max(68, 34 * (message["content"].count('\n') + 1)))
                edited_content = st.text_area("메시지 편집", message["content"], height=min(680, max(68, 34 * (message["content"].count('\n') + 1))), key=f"edit_{i}")
                col1, col2, col3 = st.columns([15, 1, 1]) #CSS스타일 따라서 조절해야함. 현재 버튼 너비 1.8rem
                with col1:
                    st.markdown("*이 메시지를 편집하면 이후의 대화 내용은 사라집니다*", unsafe_allow_html=True)
                with col2:
                    if st.button("", key=f"cancel_{i}", icon=":material/reply:", help="돌아가기"):
                        st.session_state.editing_message = None
                        st.rerun()
                with col3:
                    if st.button("", key=f"save_{i}", icon=":material/done_outline:", help="보내기"):
                        submit_edit(i, edited_content)
            else: #이미 완료된 메시지
                st.markdown(text_code_parser.render_mixed_content(message["content"])) #규칙 기반 코드블록 인식 후 출력
                

                col1, col2 = st.columns([16, 1])
                with col2:
                    # 모든 사용자 메시지에 편집 버튼 표시
                    if st.button("", key=f"edit_btn_{i}", help="이 메시지 편집", icon=":material/edit:"):
                        edit_message(i)
                        st.rerun()
        else: # 어시스턴트 메시지는 편집 불가
            st.markdown(message["content"], unsafe_allow_html=True)
           

# 편집 후 또는 새 메시지에 대한 자동 응답 생성
if ((st.session_state.generating_response or st.session_state.new_message_added) and 
    st.session_state.messages and 
    st.session_state.messages[-1]["role"] == "user"):
    
    # 플래그 초기화
    #st.session_state.generating_response = False
    st.session_state.new_message_added = False

    retries = 0
    max_retries = 3
    
    while (len(st.session_state.messages)>0 and 
           st.session_state.messages[-1]["role"] != "assistant" and 
           retries < max_retries):
        
        chat.generate_claude_response(model, temperature, system_prompt)
        retries += 1
        print(f"응답 재시도 {retries}회")
    
    if retries >= max_retries:
        st.error("응답 생성에 실패했습니다. 다시 시도해주세요.")

    st.session_state.generating_response = False
    history.save_conversation_to_db(db)

# 사용자 입력 받기
prompt = st.chat_input("무엇이든 물어보세요!")
 
if prompt:
    # 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": prompt})
    history.save_conversation_to_db(db)
    
    # 새 메시지 추가 플래그 설정
    st.session_state.new_message_added = True
    
    # 앱 재실행하여 모든 메시지를 for 루프에서 표시하도록 함
    st.rerun()

# 응답 후 히스토리 관리
with st.sidebar:
    st.markdown("""
    <style>
    div[data-testid="stTextAreaRootElement"]:has(textarea[aria-label="토큰 사용량"]) {
        display: none;
    }
    </style>""", unsafe_allow_html=True)
    _ = st.text_area("토큰 사용량", help=f"최대 사용량 ({int(max_input_token/1000)}K)에 도달 시 과거 대화부터 참조하지 않고 응답합니다.")
    
    my_bar = st.progress(0, text='토큰 사용량')
    token_in_K = st.session_state.num_input_tokens/1000
    my_bar.progress(min(st.session_state.num_input_tokens/max_input_token, 1.), text=f"{token_in_K:.2f}K input tokens ({token_in_K*0.003*1350:.1f}₩) per answer ")

    st.header(":material/import_contacts: 대화 기록 관리")
    
    if not st.session_state.user_email:
        st.write("이 기능을 사용하시려면 로그인해 주세요")
    else:
        # 최근 세션 목록 불러오기
        recent_sessions = history.get_recent_sessions(db)
        
        if recent_sessions:
            # 현재 활성화된 세션 ID 가져오기
            grouped_sessions = history.group_sessions_by_time(recent_sessions)

            for group_name, sessions_in_group in grouped_sessions.items():
                if sessions_in_group:  # 해당 그룹에 세션이 있을 때만 표시
                    st.markdown(f"#### {group_name}")
                    for i, session in enumerate(sessions_in_group):
                        session_id = session['session_id']
                        
                        # 미리보기 텍스트 처리
                        preview_text = session['preview']
                        
                        # 현재 세션인지 확인
                        is_current_session = (session_id == st.session_state.session_id)
                        
                        # 버튼 생성 (현재 세션은 비활성화)
                        button_key = f"session_{session_id}"
                        if st.button(preview_text, key=button_key, use_container_width=True, disabled=is_current_session):
                            # 선택한 세션 불러오기
                            loaded_messages = history.load_conversation_from_db(session_id, db)
                            if loaded_messages:
                                truncated_messages, num_input_tokens = chat.truncate_messages(loaded_messages, system_prompt)
                                st.session_state.messages = truncated_messages
                                st.session_state.num_input_tokens = num_input_tokens
                                st.session_state.session_id = session_id  # 현재 세션 ID 업데이트
                                st.rerun()
        else:
            st.write("이전 대화 기록이 없습니다.")
            st.write(f"현재 세션 ID: {st.session_state.session_id}")

            
    st.markdown("#### 대화내용 내보내기/불러오기")
    if st.session_state.messages:  # 대화 내용이 있을 때만 버튼 표시
        json_data, filename = history.save_conversation_as_json()
        st.download_button(
            label="JSON으로 대화 내용 내보내기",
            data=json_data,
            file_name=filename,
            mime="application/json",
            help="대화 기록을 JSON으로 다운로드하여 새 세션에서 불러와 대화를 이어갈 수 있습니다.",
            use_container_width=True)
     
    else:
        # JSON 업로드 기능 (대화가 없을 때만)
        json_input = st.text_area("📋 JSON 대화 내용 붙여넣기", placeholder="JSON 형식의 대화 내용을 붙여넣으세요...")
        if st.button("JSON으로부터 대화 불러오기", use_container_width=True):
            if json_input.strip():
                loaded_messages = history.load_conversation_from_json(json_input)
                if loaded_messages:
                    st.session_state.session_id = str(uuid.uuid4())
                    st.session_state.messages = loaded_messages
                    st.success("대화를 성공적으로 불러왔습니다!")
                    st.rerun()
                else:
                    st.error("올바른 JSON 형식이 아닙니다.")
            else:
                st.warning("JSON 내용을 입력해주세요.")
                
    st.markdown("---")
    st.markdown("Powered by Anthropic Claude")
