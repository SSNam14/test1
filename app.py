import streamlit as st
import anthropic
from anthropic import Anthropic
import os
 
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
                
        # 응답 생성 완료
        st.session_state.generating_response = False
        
    except Exception as e:
        try:
            if eval(str(e))['error']['type']=='overloaded_error':
                st.markdown("이런, Anthropic 서버가 죽어있네요.😞 잠시후에 다시 시도하거나 다른 모델을 사용해주세요")
        except:
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
    
    # 새 메시지 추가 플래그 설정
    st.session_state.new_message_added = True
    
    # 앱 재실행하여 모든 메시지를 for 루프에서 표시하도록 함
    st.rerun()

# 응답 후 히스토리 관리
with st.sidebar:
    st.header("대화 기록 관리")
    if st.button("대화 초기화"):
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
                    st.session_state.messages = loaded_messages
                    st.success("대화를 성공적으로 불러왔습니다!")
                    st.rerun()
                else:
                    st.error("올바른 JSON 형식이 아닙니다.")
            else:
                st.warning("JSON 내용을 입력해주세요.")

    st.markdown("---")
    st.markdown("Anthropic Claude API를 사용한 챗봇입니다.")
