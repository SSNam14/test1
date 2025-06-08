import streamlit as st
from anthropic import Anthropic
import os
import uuid
import firebase_admin
from firebase_admin import credentials, firestore
import streamlit.components.v1 as components
import extra_streamlit_components as stx
import time
import json
import datetime
import styles
import text_code_parser
import chat

max_input_token = chat.max_input_token
cookie_delay = 1.0

# 페이지 설정
st.set_page_config(page_title="Claude", page_icon="🤖")
st.title("Claude")

styles.style_sidebar()
styles.style_buttons()
styles.style_message()
styles.style_navigation()

# Firebase 초기화
if not firebase_admin._apps:
    cred_dict = dict(st.secrets["firebase"])
    if "private_key" in cred_dict:
        cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
db = firestore.client()

# 페이지 설정 및 쿠키 컨트롤러 초기화
cookie_manager = stx.CookieManager()

COOKIE_KEY = 'user_login'

if 'cookie_initialized' not in st.session_state:
    try:
        user_cookie = cookie_manager.get(COOKIE_KEY)
        time.sleep(cookie_delay)
        if user_cookie is not None:
            print("cookie with", user_cookie)
            st.session_state.user_email = user_cookie.get("email")
            st.session_state.user_name = user_cookie.get("name")
            st.session_state.cookie_initialized = True
        else:
            print("no cookie")
            st.session_state.cookie_initialized = True
    except Exception as e:
        print(f"Cookie error: {e}")
        st.session_state.cookie_initialized = True
    
# 사용자 인증 함수
def authenticate_user(email):
    if not email or not email.strip(): # 빈 이메일 체크
        return None

    email = email.lower().strip()
    user_doc = db.collection('users').document(email).get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        return user_data.get('name')
    return None

def login():
    email = st.session_state.email_input

    if not email or not email.strip():
        st.session_state.login_error = True
        st.session_state.error_message = "이메일을 입력해주세요."
        return

    user_name = authenticate_user(email)

    if user_name:
        st.session_state.user_email = email
        st.session_state.user_name = user_name
        st.session_state.login_error = False
        user_data = {'email': email, 'name': user_name}

        # 쿠키 설정 수정 - 클라우드 환경 고려
        expires_at = datetime.datetime.now() + datetime.timedelta(days=7)
        try:
            cookie_manager.set(
                COOKIE_KEY,
                user_data,
                expires_at=expires_at,
                secure=False,  # 로컬/클라우드 모두 호환
                same_site='lax'
            )
            time.sleep(cookie_delay)
            print("쿠키 설정 완료")
        except Exception as e:
            print(f"쿠키 설정 실패: {e}")

    else:
        st.session_state.login_error = True
        st.session_state.error_message = "등록되지 않은 이메일입니다."

def logout():
    st.session_state.user_email = None
    st.session_state.user_name = None
    st.session_state.email_input = ""
    try:
        cookie_manager.delete(COOKIE_KEY)
        time.sleep(cookie_delay)
        print("쿠키 삭제 완료")
    except Exception as e:
        print(f"쿠키 삭제 실패: {e}")
    st.rerun()
             
def save_conversation_as_json():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    timestamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d_%H%M%S")
    filename = f"conversation_{timestamp}.json"
 
    json_data = json.dumps(st.session_state.messages, ensure_ascii=False, indent=2)
    return json_data, filename

def load_conversation_from_json(json_text):
    try:
        messages = json.loads(json_text)
        # 간단한 유효성 검사
        if isinstance(messages, list) and all('role' in msg and 'content' in msg for msg in messages):
            return messages
        else:
            return None
    except:
        return None


def get_session_id_from_url():
    """URL 파라미터에서 세션 ID를 가져옵니다."""
    return st.query_params.get('session_id', None)

def set_session_id_in_url(session_id):
    """URL에 세션 ID를 설정합니다."""
    st.query_params['session_id'] = session_id


# 대화 저장 함수 (수정)
def save_conversation_to_db():
    if not st.session_state.messages:
        return
    if not st.session_state.user_email: 
        user_email = 'anonymous'
        user_name = 'anonymous'
    else:
        user_email = st.session_state.user_email
        user_name = st.session_state.user_name
    
    try:
        session_ref = db.collection('conversations') \
                        .document(user_email) \
                        .collection('sessions') \
                        .document(st.session_state.session_id)

        data = {
            'messages': st.session_state.messages,
            'updated_at': firestore.SERVER_TIMESTAMP,
            'session_id': st.session_state.session_id,
            'user_email': user_email,
            'user_name': user_name
        }

        # preview 조건: user 메시지가 2개 이상 & preview가 없을 때 & 로그인한 사용자에 한해서만
        user_messages = [m for m in st.session_state.messages if m.get("role") == "user"]
        if (len(user_messages) >= 2) and ('user_email' in st.session_state): 
            existing_doc = session_ref.get()
            if not existing_doc.exists or 'preview' not in existing_doc.to_dict():
                preview = chat.get_preview_with_claude(st.session_state.messages)
                data['preview'] = preview

        session_ref.set(data, merge=True)
        return True
    except Exception as e:
        print(f"대화 저장 오류: {str(e)}")
        return False


def load_conversation_from_db(session_id):
    if 'user_email' not in st.session_state: 
        user_email = 'anonymous'
        user_name = 'anonymous'
    else:
        user_email = st.session_state.user_email
        user_name = st.session_state.user_name        
    print("loading from db (1)", user_email, user_name)        

    try:
        doc_ref = db.collection('conversations') \
                    .document(user_email) \
                    .collection('sessions') \
                    .document(session_id)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            st.session_state.session_id = session_id
            messages = data.get('messages', [])
            set_session_id_in_url(session_id)

            # preview가 없고 메시지가 2개 이상이고 로그인한 사용자에 한해서 생성
            if 'preview' not in data and len(messages) >= 2 and 'user_email' in st.session_state:
                preview = chat.get_preview_with_claude(messages)
                doc_ref.update({'preview': preview})
                
            return messages
        else:
            st.warning(f"세션 ID {session_id}에 해당하는 대화를 찾을 수 없습니다.")
            return []
    except Exception as e:
        st.error(f"대화 불러오기 오류: {str(e)}")
        return []

def get_recent_sessions(limit=40):
    """최근 세션 목록을 가져오는 함수"""
    if not st.session_state.user_email:
        return []
    
    try:
        sessions_ref = db.collection('conversations') \
                         .document(st.session_state.user_email) \
                         .collection('sessions')
        query = sessions_ref.order_by('updated_at', direction=firestore.Query.DESCENDING).limit(limit)
        sessions = list(query.stream())
        
        result = []
        for session in sessions:
            session_id = session.id
            data = session.to_dict()
            
            # preview 결정
            preview = data.get('preview', "New Chat").strip().split('\n')[0]
            
            result.append({
                'session_id': session_id,
                'preview': preview,
                'updated_at': data.get('updated_at')
            })
        
        return result
        
    except Exception as e:
        st.error(f"세션 로딩 중 오류 발생: {str(e)}")
        return []
    
if 'session_id' not in st.session_state:
    url_session_id = get_session_id_from_url()
    
    if url_session_id:
        # URL에 session_id가 있으면 사용
        st.session_state.session_id = url_session_id
        print(f"Using session_id from URL: {url_session_id}")
        st.session_state.messages = load_conversation_from_db(url_session_id)
    else:
        # URL에 없으면 새로 생성하고 URL에 설정
        new_session_id = str(uuid.uuid4())
        st.session_state.session_id = new_session_id
        set_session_id_in_url(new_session_id)
        print(f"Generated new session_id: {new_session_id}")        

# 세션 ID 관리 (추가)
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

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
            logout()
                
    else: # 로그인되지 않은 상태
        st.text_input("이메일 주소", key="email_input", placeholder='abcd@gmail.com', label_visibility='collapsed')
        
        if st.button(":material/login: 로그인", key="login_btn", use_container_width=True, help="로그인하시면 대화 기록이 저장됩니다."):
            login()
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

    # 이 메시지 이후의 모든 메시지 삭제
    st.session_state.messages = st.session_state.messages[:message_index + 1]

    # 편집 상태 초기화
    st.session_state.editing_message = None

    # 응답 생성 필요성 표시
    st.session_state.generating_response = True

    # DB에 저장
    save_conversation_to_db()

    # 앱 재실행
    st.rerun()


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

n_user_messages = 0
for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(f'<div id="msg-{n_user_messages}" style="scroll-margin-top: 70px;"></div>',  unsafe_allow_html=True)
            n_user_messages+=1

            # 편집 중인 메시지
            if st.session_state.editing_message == i:
                height = min(680, max(68, 34 * (message["content"].count('\n') + 1)))
                print(height)
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
        else:
            # 어시스턴트 메시지는 편집 불가
            st.markdown(message["content"], unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
            

# 편집 후 또는 새 메시지에 대한 자동 응답 생성
if ((st.session_state.generating_response or st.session_state.new_message_added) and 
    st.session_state.messages and 
    st.session_state.messages[-1]["role"] == "user"):
    
    # 플래그 초기화
    st.session_state.generating_response = False
    st.session_state.new_message_added = False
    
    chat.generate_claude_response(model, temperature, system_prompt)
    save_conversation_to_db()

# 사용자 입력 받기
prompt = st.chat_input("무엇이든 물어보세요!")
 
if prompt:
    # 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_conversation_to_db()
    
    # 새 메시지 추가 플래그 설정
    st.session_state.new_message_added = True
    
    # 앱 재실행하여 모든 메시지를 for 루프에서 표시하도록 함
    st.rerun()

from datetime import timezone, timedelta

def group_sessions_by_time(recent_sessions):
    # 사용자의 시간대를 고려하는 것이 가장 좋지만,
    # 여기서는 서버/DB 기준인 UTC로 일관성 있게 처리합니다.
    # 한국 사용자 대상이라면 'Asia/Seoul'로 하는 것도 방법입니다.
    # from zoneinfo import ZoneInfo
    # tz = ZoneInfo("Asia/Seoul")
    # now = datetime.datetime.now(tz)
    
    now = datetime.datetime.now(timezone.utc)
    today_date = now.date()
    yesterday_date = today_date - timedelta(days=1)
    
    # 그룹을 동적으로 생성하기 위해 defaultdict 사용
    from collections import defaultdict
    time_groups = defaultdict(list)

    # 정렬된 순서를 유지하기 위한 그룹 키 리스트
    group_order = ['오늘', '어제', '이전 7일', '이전 30일']
    
    for session in recent_sessions:
        timestamp = session.get('updated_at')
        if not timestamp:
            time_groups['오래 전'].append(session)
            continue

        try:
            # Firestore 타임스탬프 처리 (기존 로직 유지)
            if hasattr(timestamp, 'seconds'):
                dt = datetime.datetime.fromtimestamp(timestamp.seconds, tz=timezone.utc)
            elif hasattr(timestamp, 'strftime'):
                dt = timestamp
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            elif isinstance(timestamp, dict) and 'seconds' in timestamp:
                dt = datetime.datetime.fromtimestamp(timestamp['seconds'], tz=timezone.utc)
            else:
                raise ValueError("Unknown timestamp format")

            session_date = dt.date()
            days_diff = (today_date - session_date).days

            group_key = ''
            if days_diff == 0:
                group_key = '오늘'
            elif days_diff == 1:
                group_key = '어제'
            elif 1 < days_diff <= 7:
                group_key = '이전 7일'
            elif 7 < days_diff <= 30:
                group_key = '이전 30일'
            else:
                # 30일이 넘어가면 'YYYY년 MM월' 형식으로 그룹화
                group_key = dt.strftime('%Y년 %m월')
            
            time_groups[group_key].append(session)

        except (ValueError, TypeError, OSError):
            time_groups['오래 전'].append(session)

    # 월별 그룹을 시간 순으로 정렬하기 위해 처리
    final_ordered_groups = {}
    
    # 기본 순서 그룹 추가
    for key in group_order:
        if key in time_groups:
            final_ordered_groups[key] = time_groups.pop(key)
    
    # 나머지 월별 그룹들을 시간 역순으로 정렬
    monthly_keys = sorted(time_groups.keys(), reverse=True)
    for key in monthly_keys:
        final_ordered_groups[key] = time_groups[key]

    return final_ordered_groups

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
        recent_sessions = get_recent_sessions()
        
        if recent_sessions:
            # 현재 활성화된 세션 ID 가져오기
            grouped_sessions = group_sessions_by_time(recent_sessions)

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
                            loaded_messages = load_conversation_from_db(session_id)
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
        json_data, filename = save_conversation_as_json()
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
                loaded_messages = load_conversation_from_json(json_input)
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
