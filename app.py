import streamlit as st
import anthropic
from anthropic import Anthropic
import os
import re
import uuid
import firebase_admin
from firebase_admin import credentials, firestore
import extra_streamlit_components as stx
import time
import json
import datetime

max_input_token = 40000

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
        margin-left: 2px;
        cursor: pointer;
    }

    /* 일반 요소들 세로 여백 줄이기 */
    .element-container {
        margin-bottom: 0.0rem;
    }

    /* 텍스트 입력 필드 여백 */
    .stTextInput > div > div > input {
        padding: 0.4rem;
    }
</style>
""", unsafe_allow_html=True)

# Firebase 초기화
if not firebase_admin._apps:
    cred_dict = dict(st.secrets["firebase"])
    if "private_key" in cred_dict:
        cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
db = firestore.client()

api_key = st.secrets['ANTHROPIC_API_KEY']


client = Anthropic(api_key=api_key)

# 페이지 설정 및 쿠키 컨트롤러 초기화
cookie_manager = stx.CookieManager()

COOKIE_KEY = 'user_login'

if 'cookie_initialized' not in st.session_state:
    try:
        user_cookie = cookie_manager.get(COOKIE_KEY)
        time.sleep(0.5)
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

if 'num_input_tokens' not in st.session_state:
    st.session_state.num_input_tokens = 0

def escape_literal_newlines_fixed(code: str) -> str:
    """
    문자열 리터럴 내의 실제 개행문자를 \\n으로 이스케이프합니다.
    """
    def esc_string_literals(match):
        literal = match.group(0)
        # 실제 개행문자(아스키 10)를 문자열 \\n으로 변환
        literal = literal.replace("\n", "\\n")
        return literal
    
    # 따옴표로 둘러싸인 문자열 리터럴들을 찾아서 처리
    # 삼중 따옴표, 단일/이중 따옴표 모두 처리
    code = re.sub(r'""".*?"""', esc_string_literals, code, flags=re.DOTALL)
    code = re.sub(r"'''.*?'''", esc_string_literals, code, flags=re.DOTALL)
    code = re.sub(r'"(?:[^"\\]|\\.)*"', esc_string_literals, code)
    code = re.sub(r"'(?:[^'\\]|\\.)*'", esc_string_literals, code)
    
    return code

def is_code_line(line: str) -> bool:
    stripped = line.strip()
    
    # 빈 줄은 컨텍스트에 따라 판단하도록 별도 처리
    if not stripped:
        return None  # 빈 줄은 컨텍스트로 판단
        
    if re.match(r'^[\(\)\[\]\{\}\s,]*$', stripped) and any(c in stripped for c in "(){}[]"):
        return True        
    
    # 명확한 코드 패턴들
    if (
        bool(re.match(r"^(for|if|elif|else|while|def|class|try|except|finally|with|async\s+def|await|match|case|return|yield|raise|break|continue|pass|import|from|global|nonlocal|assert)\b", stripped))
        or stripped.startswith("#")
        or stripped.startswith("@")
        or line.startswith(" ") or line.startswith("\t")  # 들여쓰기된 줄
    ):
        return True
    
    # 함수 호출 패턴 (더 엄격하게)
    if bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_\.]*\s*\([^)]*\)\s*$", stripped)):
        return True
    
    # 변수 할당 패턴 (더 엄격하게)
    if bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_,\s]*\s*=\s*.+", stripped)):
        return True
    
    # 괄호가 있지만 일반 문장일 가능성이 높은 경우들을 제외
    if any(c in stripped for c in "(){}[]"):
        # 문장 중간에 괄호가 있는 경우 (예: "이것은 (예시) 문장입니다") 제외
        if (stripped.count('(') == stripped.count(')') and 
            not stripped.startswith('(') and 
            not stripped.endswith(')') and
            not any(stripped.startswith(op) for op in ['if ', 'for ', 'while ', 'def ', 'class ']) and
            not bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_\.]*\s*\(", stripped))):
            return False
        return True
    
    return False

def render_mixed_content(content: str):
    lines = content.splitlines()
    current_block = []
    current_type = None  # "code" or "text"
    
    def flush():
        nonlocal current_block, current_type
        if not current_block:
            return
        text = "\n".join(current_block)
        if current_type == "code":
            text = escape_literal_newlines_fixed(text)
            st.code(text, language="python")
        else:
            st.markdown(f'<div style="white-space: pre-wrap;">{text}</div>', unsafe_allow_html=True)
        current_block = []
    
    # 빈 줄 처리를 위한 컨텍스트 분석
    processed_lines = []
    for i, line in enumerate(lines):
        line_type = is_code_line(line)
        if line_type is None:  # 빈 줄인 경우
            # 앞뒤 줄의 타입을 확인
            prev_type = None
            next_type = None
            
            # 이전 비어있지 않은 줄 찾기
            for j in range(i-1, -1, -1):
                prev_check = is_code_line(lines[j])
                if prev_check is not None:
                    prev_type = prev_check
                    break
            
            # 다음 비어있지 않은 줄 찾기
            for j in range(i+1, len(lines)):
                next_check = is_code_line(lines[j])
                if next_check is not None:
                    next_type = next_check
                    break
            
            # 앞뒤가 모두 코드이면 빈 줄도 코드로 처리
            if prev_type is True and next_type is True:
                line_type = True
            else:
                line_type = False
        
        processed_lines.append((line, line_type))
    
    # 블록 단위로 처리
    for line, this_is_code in processed_lines:
        new_type = "code" if this_is_code else "text"
        
        if current_type is None:
            current_type = new_type
        
        if new_type != current_type:
            flush()
            current_type = new_type
        
        current_block.append(line)
    
    flush()

    
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
            time.sleep(0.5)
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
        print("쿠키 삭제 완료")
    except Exception as e:
        print(f"쿠키 삭제 실패: {e}")
    st.rerun()

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

#토큰 카운팅
def count_token(model, system, messages):
    response = client.messages.count_tokens(
        model=model,
        system=system,
        messages=messages,
    )
    return int(dict(response)['input_tokens'])

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
    if st.button("테스트 쿠키 설정"):
        cookie_manager.set('test_cookie', 'test_value')
        time.sleep(0.5)
        st.write("테스트 쿠키 설정 완료")

    if st.session_state.user_email: # 로그인된 상태
        st.markdown(f'<p style="margin:0.2; line-height:2.5;">안녕하세요, {st.session_state.user_name}님! 👋</p>', unsafe_allow_html=True)
        if st.button("로그아웃", key="logout_btn", use_container_width=True,):
            logout()
                
    else: # 로그인되지 않은 상태
        st.text_input("이메일 주소", key="email_input", placeholder='abcd@gmail.com', label_visibility='collapsed')
        
        if st.button("로그인", key="login_btn", use_container_width=True, help="로그인하시면 대화 기록이 저장됩니다."):
            login()
            st.rerun()  # 로그인 후 즉시 페이지 새로고침

        if 'login_error' in st.session_state and st.session_state.login_error:
            st.error(st.session_state.error_message)
    
    
    st.header("⚙️ 응답 설정")
    model = st.selectbox(
        "모델 선택",
        ["claude-sonnet-4-20250514", "claude-3-7-sonnet-20250219", "claude-opus-4-20250514", "claude-3-opus-20240229", ]
    )
    
    temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.7, step=0.1, 
                            help="값이 높을수록 창의적이고 다양한 답변, 낮을수록 일관되고 예측 가능한 답변")
    
    #max_tokens = st.slider("max_tokens", min_value=1, max_value=8128, value=2048, step=1, 
    #                       help="응답의 최대 토큰 수 (대략 단어 수). 긴 답변이 필요하면 높게 설정")

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
                render_mixed_content(message["content"]) #규칙 기반 코드블록 인식 후 출력

                col1, col2 = st.columns([10, 1])
                with col2:
                    # 모든 사용자 메시지에 편집 버튼 표시
                    if st.button("✏️", key=f"edit_btn_{i}", help="이 메시지 편집"):
                        edit_message(i)
                        st.rerun()
        else:
            # 어시스턴트 메시지는 편집 불가
            st.markdown(message["content"], unsafe_allow_html=True)

def truncate_messages(messages, max_tokens=max_input_token):
    """토큰 사용량 추산을 통해 효율적으로 대화 길이 제한"""
    if len(messages) == 0:
        return messages

    # 현재 전체 토큰 수 계산
    current_tokens = count_token(model, system_prompt, messages)

    # 토큰 수가 제한 이하면 전체 반환
    if current_tokens <= max_tokens:
        return messages, current_tokens

    # 토큰 수가 초과하면 비례적으로 대화 수 줄이기
    total_conversations = len(messages) // 2  # user+assistant 쌍의 개수
    if total_conversations == 0:
        return messages, current_tokens

    # 유지할 대화 수 계산 (최소 1개는 보장)
    keep_conversations = max(1, int(total_conversations * (max_tokens / current_tokens)))

    # 최근 N개 대화만 유지 (user+assistant 쌍 단위)
    keep_messages_count = keep_conversations * 2
    truncated_messages = messages[-keep_messages_count:]
    return truncated_messages, int(current_tokens * (max_tokens / current_tokens))


#응답 생성 함수 - 중복을 방지하기 위해 함수로 분리
def generate_claude_response():
    # 메시지 기록 준비
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
    ]
    truncated_messages, num_input_tokens = truncate_messages(messages, max_tokens=max_input_token)
    st.session_state.num_input_tokens = num_input_tokens
    
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
                    messages=truncated_messages,
                    temperature=temperature,
                    max_tokens=64000,
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
        if eval(str(e))['error']['type']=='overloaded_error':
            st.error("이런, Anthropic 서버가 죽어있네요😞 잠시 후 다시 시도하거나 다른 모델을 사용해 주세요")
        else:
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
    my_bar = st.progress(0, text='토큰 사용량')
    token_in_K = st.session_state.num_input_tokens/1000
    my_bar.progress(min(st.session_state.num_input_tokens/max_input_token, 1.), text=f'{token_in_K:.2f}K tokens as input, {token_in_K*0.003*1350:.1f}₩ per answer')

    st.header("📖 대화 기록 관리")

    if st.button("대화 초기화", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

    st.markdown("#### 이전 대화")
    if not st.session_state.user_email:
        st.write("이 기능을 사용하시려면 로그인해 주세요")

    else:
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
                button_text = f"{i+1}. {preview_text.replace('\n', ' ')}"
        
                # 클릭 가능한 버튼으로 만들기
                button_key = f"session_{session['session_id']}"
                if st.button(button_text, key=button_key, use_container_width=True):
                    # 선택한 세션 불러오기
                    loaded_messages = load_conversation_from_db(session['session_id'])
                    if loaded_messages:
                        _, st.session_state.num_input_tokens = truncate_messages(loaded_messages, 10000000) #대화 불러오자마자 계산
                        st.session_state.messages = loaded_messages
                        st.success("이전 대화를 불러왔습니다!")
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
