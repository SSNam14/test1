import streamlit as st
import anthropic
from anthropic import Anthropic
import os
import uuid
import firebase_admin
from firebase_admin import credentials, firestore

# 페이지 설정
st.set_page_config(page_title="Claude", page_icon="🤖")
st.title("Claude")

st.markdown("""
<style>
    /* 채팅 메시지 컨테이너 간격 줄이기 */
    .stChatMessage {
        padding-top: 2px !important;
        padding-bottom: 2px !important;
        margin-top: 2px !important;
        margin-bottom: 2px !important;
    }

    /* 메시지 내용 간격 줄이기 */
    .stChatMessage > div {
        padding-top: 2px !important;
        padding-bottom: 2px !important;
    }

    /* 메시지 안의 마크다운 간격 줄이기 */
    .stMarkdown {
        padding-top: 0px !important;
        padding-bottom: 0px !important;
        margin-top: 0px !important;
        margin-bottom: 0px !important;
    }
    
    /* 편집 버튼 스타일 */
    .edit-button {
        font-size: 0.8rem;
        color: #888;
        margin-left: 5px;
        cursor: pointer;
    }
</style>
""", unsafe_allow_html=True)

# Firebase 초기화
if not firebase_admin._apps:
    cred_dict = dict(st.secrets["firebase"])
    
    # private_key의 개행 문자 처리
    if "private_key" in cred_dict:
        cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
    
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
db = firestore.client()

# 세션 ID 관리 (추가)
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# 세션 상태 초기화
if 'messages' not in st.session_state:
    st.session_state.messages = []

# 편집 관련 상태 변수 초기화
if 'editing_message' not in st.session_state:
    st.session_state.editing_message = None

# 새 응답 생성 중 상태 추적
if 'generating_response' not in st.session_state:
    st.session_state.generating_response = False

# 새 메시지 추가 확인 플래그
if 'new_message_added' not in st.session_state:
    st.session_state.new_message_added = False

# 로그인 상태 관리
if 'user_email' not in st.session_state:
    st.session_state.user_email = None

if 'user_name' not in st.session_state:
    st.session_state.user_name = None

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

# 로그인/로그아웃 함수
def login():
    email = st.session_state.email_input

    if not email or not email.strip(): # 빈 이메일 체크
        st.session_state.login_error = True
        st.session_state.error_message = "이메일을 입력해주세요."
        return

    user_name = authenticate_user(email)

    if user_name:
        st.session_state.user_email = email
        st.session_state.user_name = user_name
        st.session_state.login_error = False
    else:
        st.session_state.login_error = True
        st.session_state.error_message = "등록되지 않은 이메일입니다."

def logout():
    st.session_state.user_email = None
    st.session_state.user_name = None
    st.session_state.email_input = ""
    st.rerun()  # 즉시 페이지 새로고침

def claude_stream_generator(response_stream):
    """Claude API의 스트리밍 응답을 텍스트 제너레이터로 변환합니다."""
    for chunk in response_stream:
        if hasattr(chunk, 'type'):
            # content_block_delta 이벤트 처리
            if chunk.type == 'content_block_delta' and hasattr(chunk, 'delta') and hasattr(chunk.delta, 'text'):
                yield chunk.delta.text
            # content_block_start 이벤트 처리
            elif chunk.type == 'content_block_start' and hasattr(chunk, 'content_block') and hasattr(chunk.content_block, 'text'):
                yield chunk.content_block.text
             
def save_conversation_as_json():
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    timestamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d_%H%M%S")
    filename = f"conversation_{timestamp}.json"
 
    json_data = json.dumps(st.session_state.messages, ensure_ascii=False, indent=2)
    return json_data, filename

def load_conversation_from_json(json_text):
    import json
    try:
        messages = json.loads(json_text)
        # 간단한 유효성 검사
        if isinstance(messages, list) and all('role' in msg and 'content' in msg for msg in messages):
            return messages
        else:
            return None
    except:
        return None

# 대화 저장 함수 (수정)
def save_conversation_to_db():
    if not st.session_state.user_email or not st.session_state.messages:
        return

    try:
        # 현재 세션의 대화 저장 (session_id 사용)
        db.collection('conversations').document(st.session_state.user_email).collection('sessions').document(st.session_state.session_id).set({
            'messages': st.session_state.messages,
            'updated_at': firestore.SERVER_TIMESTAMP,
            'session_id': st.session_state.session_id,
            'user_email': st.session_state.user_email,
            'user_name': st.session_state.user_name
        })
        return True
    except Exception as e:
        print(f"대화 저장 오류: {str(e)}")
        return False

# 대화 불러오기 함수 (추가)
def load_conversation_from_db(session_id):
    if not st.session_state.user_email:
        return None

    try:
        # 특정 세션의 대화 불러오기
        doc = db.collection('conversations').document(st.session_state.user_email).collection('sessions').document(session_id).get()

        if doc.exists:
            data = doc.to_dict()
            # 불러온 세션의 ID로 현재 세션 ID 변경
            st.session_state.session_id = session_id
            return data.get('messages', [])
        else:
            st.warning(f"세션 ID {session_id}에 해당하는 대화를 찾을 수 없습니다.")
            return []
    except Exception as e:
        st.error(f"대화 불러오기 오류: {str(e)}")
        return []
        
def get_recent_sessions(limit=10):
    if not st.session_state.user_email:
        return []

    # 디버깅 정보 초기화
    debug_info = {
        'current_session_id': st.session_state.session_id,
        'user_email': st.session_state.user_email,
        'all_sessions': []
    }

    try:
        # 모든 세션 가져오기 (현재 세션 포함)
        sessions_ref = db.collection('conversations').document(st.session_state.user_email).collection('sessions')
        query = sessions_ref.order_by('updated_at', direction=firestore.Query.DESCENDING).limit(limit)
        sessions = list(query.stream())  # 리스트로 변환하여 세션 수 확인 가능

        debug_info['total_sessions_found'] = len(sessions)

        result = []
        for idx, session in enumerate(sessions):
            session_id = session.id  # 문서 ID 사용
            data = session.to_dict()

            # 모든 세션 정보 저장 (디버깅용)
            session_data = {
                'session_id': session_id,
                'is_current': session_id == st.session_state.session_id,
                'updated_at': str(data.get('updated_at')),
                'message_count': len(data.get('messages', [])),
            }
            debug_info['all_sessions'].append(session_data)

            # 현재 세션 제외
            if session_id == st.session_state.session_id:
                continue

            # 첫 번째 메시지 내용으로 미리보기 생성
            preview = f"세션 {idx+1}"
            messages = data.get('messages', [])

            if messages:
                # 사용자 메시지 찾기
                user_messages = [msg for msg in messages if msg.get('role') == 'user']
                if user_messages:
                    first_msg = user_messages[0].get('content', '')
                    preview = first_msg[:30] + ('...' if len(first_msg) > 30 else '')

            # 타임스탬프 정보 추가
            timestamp_info = ""
            if data.get('updated_at'):
                try:
                    # Firestore 타임스탬프 처리 방법 수정
                    timestamp = data.get('updated_at')
            
                    # Firestore 타임스탬프 객체인 경우
                    if hasattr(timestamp, 'seconds'):
                        import datetime
                        dt = datetime.datetime.fromtimestamp(timestamp.seconds)
                        timestamp_info = f" ({dt.strftime('%m/%d %H:%M')})"
                    # 이미 datetime 객체인 경우
                    elif hasattr(timestamp, 'strftime'):
                        timestamp_info = f" ({timestamp.strftime('%m/%d %H:%M')})"
                    # 딕셔너리 형태인 경우 (JSON 변환 후)
                    elif isinstance(timestamp, dict) and 'seconds' in timestamp:
                        import datetime
                        dt = datetime.datetime.fromtimestamp(timestamp['seconds'])
                        timestamp_info = f" ({dt.strftime('%m/%d %H:%M')})"
                    else:
                        # 그 외의 경우 타입 정보 출력
                        timestamp_info = f" ({type(timestamp).__name__})"
                except Exception as e:
                    timestamp_info = f" (날짜 변환 오류: {str(e)[:20]})"

            # 고유한 ID를 포함한 미리보기 생성
            display_text = f"{preview}{timestamp_info} [ID: {session_id[-6:]}]"

            result.append({
                'session_id': session_id,
                'preview': display_text,
                'updated_at': data.get('updated_at')
            })

        debug_info['result_sessions'] = len(result)
        return result, debug_info

    except Exception as e:
        return [], {'error': str(e)}


# 세션 상태 초기화
if 'messages' not in st.session_state:
    st.session_state.messages = []

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
    st.header("👤 사용자 로그인")

    if st.session_state.user_email:
        # 로그인된 상태
        st.success(f"안녕하세요, {st.session_state.user_name}님! 👋")

        if st.button("로그아웃", key="logout_btn"):
            logout()
    else:
        # 로그인되지 않은 상태
        st.text_input("이메일 주소", key="email_input", autocomplete="text")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("로그인", key="login_btn", use_container_width=True, placeholder='abcd@gmail.com 으로 로그인하시면 대화 기록이 저장됩니다', label_visibility='hidden'):
                login()
                st.rerun()  # 로그인 후 즉시 페이지 새로고침

        if 'login_error' in st.session_state and st.session_state.login_error:
            st.error(st.session_state.error_message)
    
    api_key = st.secrets['ANTHROPIC_API_KEY']
    
    st.header("응답 설정")
    model = st.selectbox(
        "모델 선택",
        ["claude-sonnet-4-20250514", "claude-3-7-sonnet-20250219", "claude-opus-4-20250514", "claude-3-opus-20240229", ]
    )
    
    temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.7, step=0.1, 
                            help="값이 높을수록 창의적이고 다양한 답변, 낮을수록 일관되고 예측 가능한 답변")
    
    max_tokens = st.slider("max_tokens", min_value=1, max_value=4096, value=1024, step=1, 
                           help="응답의 최대 토큰 수 (대략 단어 수). 긴 답변이 필요하면 높게 설정")

    system_prompt = st.text_area("시스템 프롬프트", "간결하게")
    st.markdown("---")


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

# 이전 메시지 표시
for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            # 편집 중인 메시지
            if st.session_state.editing_message == i:
                edited_content = st.text_area("메시지 편집", message["content"], key=f"edit_{i}")
                col1, col2, col3 = st.columns([7.8, 1.1, 1.1])
                with col1:
                    st.markdown("*이 메시지를 편집하면 이후의 대화 내용은 사라집니다*", unsafe_allow_html=True)
                with col2:
                    if st.button("저장", key=f"save_{i}"):
                        submit_edit(i, edited_content)
                with col3:
                    if st.button("취소", key=f"cancel_{i}"):
                        st.session_state.editing_message = None
                        st.rerun()
            else:
                # 일반 메시지 표시 + 편집 버튼
                col1, col2 = st.columns([10, 1])
                with col1:
                    st.markdown(message["content"], unsafe_allow_html=True)
                with col2:
                    # 모든 사용자 메시지에 편집 버튼 표시
                    if st.button("✏️", key=f"edit_btn_{i}", help="이 메시지 편집"):
                        edit_message(i)
                        st.rerun()
        else:
            # 어시스턴트 메시지는 편집 불가
            st.markdown(message["content"], unsafe_allow_html=True)

#응답 생성 함수 - 중복을 방지하기 위해 함수로 분리
def generate_claude_response():
    # 메시지 기록 준비
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
    ]
    
    # Anthropic 클라이언트 생성
    client = Anthropic(api_key=api_key)
    
    try:
        # API 호출
        with st.spinner("Claude가 응답 중..."):
            # 새로운 chat_message 컨테이너 생성
            with st.chat_message("assistant"):
                # 초기 텍스트를 빈 문자열로 설정
                response_placeholder = st.empty()
                response_placeholder.markdown("")
                
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=messages,
                    temperature=temperature,
                    system=system_prompt,
                    stream=True
                )
                
                # 응답 스트리밍
                full_response = ""
                for text in claude_stream_generator(response):
                    full_response += text
                    # 응답 업데이트
                    response_placeholder.markdown(full_response)
                
                # 메시지 기록에 추가
                st.session_state.messages.append({"role": "assistant", "content": full_response})
                save_conversation_to_db()
                
        # 응답 생성 완료
        st.session_state.generating_response = False
        
    except Exception as e:
        st.error(f"오류가 발생했습니다: {str(e)}")
        st.session_state.generating_response = False

# 편집 후 또는 새 메시지에 대한 자동 응답 생성
if ((st.session_state.generating_response or st.session_state.new_message_added) and 
    st.session_state.messages and 
    st.session_state.messages[-1]["role"] == "user"):
    
    # 플래그 초기화
    st.session_state.generating_response = False
    st.session_state.new_message_added = False
    
    generate_claude_response()

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

# 응답 후 히스토리 관리
with st.sidebar:
    st.header("대화 기록 관리")
    if st.button("대화 초기화"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
     
    if st.session_state.messages:  # 대화 내용이 있을 때만 버튼 표시
        json_data, filename = save_conversation_as_json()
        st.download_button(
            label="💾 대화 내용 저장 (JSON)",
            data=json_data,
            file_name=filename,
            mime="application/json",
            help="대화 기록을 JSON으로 다운로드하여 새 세션에서 불러와 대화를 이어갈 수 있습니다."
        )
     
    else:
        # JSON 업로드 기능 (대화가 없을 때만)
        json_input = st.text_area("📋 JSON 대화 내용 붙여넣기", placeholder="JSON 형식의 대화 내용을 붙여넣으세요...")
        if st.button("대화 불러오기"):
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

    if st.session_state.user_email:
        st.header("💬 이전 대화")
    
        # 최근 세션 목록 불러오기
        recent_sessions, debug_info = get_recent_sessions()
    
        # 디버깅 정보 표시
        #with st.expander("디버깅 정보 (문제 해결용)"):
        #    st.json(debug_info)
    
        if recent_sessions:
            st.write(f"최근 대화 기록 ({len(recent_sessions)}개):")
        
            # 각 세션을 클릭 가능한 버튼으로 표시
            for i, session in enumerate(recent_sessions):
                # 미리보기 텍스트 더 짧게 만들기 (20자로 제한)
                preview_text = session['preview']
                if '(' in preview_text:  # 날짜 정보 앞부분만 유지
                    preview_text = preview_text.split('(')[0].strip()
        
                # 너무 긴 경우 잘라내기
                if len(preview_text) > 20:
                    preview_text = preview_text[:20] + "..."
        
                # 버튼 텍스트 생성 (번호 + 짧은 미리보기)
                button_text = f"{i+1}. {preview_text}"
        
                # 클릭 가능한 버튼으로 만들기
                if st.button(button_text, key=f"session_{session['session_id']}"):
                    # 선택한 세션 불러오기
                    loaded_messages = load_conversation_from_db(session['session_id'])
                    if loaded_messages:
                        st.session_state.messages = loaded_messages
                        st.success("이전 대화를 불러왔습니다!")
                        st.rerun()
        else:
            st.write("이전 대화 기록이 없습니다.")
            st.write(f"현재 세션 ID: {st.session_state.session_id}")
                
    st.markdown("---")
    st.markdown("Anthropic Claude API를 사용한 챗봇입니다.")
