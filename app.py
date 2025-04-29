import streamlit as st
import anthropic
from anthropic import Anthropic
import os
 
# 페이지 설정
st.set_page_config(page_title="Claude 챗봇", page_icon="🤖")
st.title("Claude 챗봇")
 
# 세션 상태 초기화
if 'messages' not in st.session_state:
    st.session_state.messages = []
 
# 사이드바에 API 키 입력 필드와 모델 설정 추가
with st.sidebar:
    st.header("API 설정")
    
    # Anthropic API 키 설정
    # 보안을 위해 .streamlit/secrets.toml 파일이나 환경 변수에서 가져오는 것이 좋습니다
    if 'ANTHROPIC_API_KEY' in st.secrets:
        api_key = st.secrets['ANTHROPIC_API_KEY']
    else:
        api_key = st.text_input("Anthropic API 키를 입력하세요:", type="password", key="api_key_input")
        if not api_key:
            st.warning("API 키를 입력해주세요!")
            st.stop()
    
    st.header("모델 설정")
    model = st.selectbox(
        "모델 선택",
        ["claude-3-7-sonnet-20250219", "claude-3-5-sonnet-20240620", "claude-3-opus-20240229"]
    )
    
    temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.7, step=0.1)
    
    if st.button("대화 초기화"):
        st.session_state.messages = []
        st.experimental_rerun()
    
    st.markdown("---")
    st.markdown("Anthropic Claude API를 사용한 챗봇입니다.")

st.markdown("""
<style>
    .chat_message {
        padding-top: 1px !important;    /* 상단 여백 */
        padding-bottom: 1px !important; /* 하단 여백 */
    }
</style>
""", unsafe_allow_html=True)

# 이전 메시지 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)
 
# 사용자 입력 받기
prompt = st.chat_input("무엇이든 물어보세요!")
 
if prompt:
    # 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt, unsafe_allow_html=True)
    
    # Anthropic 클라이언트 생성
    client = Anthropic(api_key=api_key)
    
    # 응답 생성
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        # 메시지 기록 준비
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages
        ]
        
        try:
            # API 호출
            with st.spinner("Claude가 생각 중..."):
                response = client.messages.create(
                    model=model,  # 사이드바에서 선택한 모델 사용
                    max_tokens=1000,
                    messages=messages,
                    temperature=temperature,  # 사이드바에서 설정한 temperature 사용
                )
                
                full_response = response.content[0].text
                message_placeholder.markdown(full_response)
                
            # 어시스턴트 응답 저장
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            
        except Exception as e:
            st.error(f"오류가 발생했습니다: {str(e)}")
