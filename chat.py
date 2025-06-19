import streamlit as st
from anthropic import Anthropic

max_input_token=40000

client = Anthropic(api_key=st.secrets['ANTHROPIC_API_KEY'])

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

def get_preview_with_claude(messages):
    user_messages = [m['content'] for m in messages if m.get('role') == 'user']
    message_in_string = "\n".join(f"- {msg}" for msg in user_messages[:5]) 

    prompt = f"""다음 대화의 제목을 한글 10자 이내 또는 영어 20자 이내로 작성하세요. 제목만 출력하고 다른 텍스트는 절대 포함하지 마세요. 
               {message_in_string}
              제목:"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=64,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip().split('\n')[0]

#입력 토큰 카운팅
def count_token(model, system, messages):
    response = client.messages.count_tokens(
        model=model,
        system=system,
        messages=messages,
    )
    return int(dict(response)['input_tokens'])


def truncate_messages(messages, system_prompt, max_tokens=max_input_token):
    """토큰 사용량 추산을 통해 효율적으로 대화 길이 제한"""
    if len(messages) == 0:
        return messages

    # 현재 전체 토큰 수 계산
    current_tokens = count_token("claude-sonnet-4-20250514", system_prompt, messages)

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
        

def generate_claude_response(model, temperature, system_prompt):
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
    ]
    truncated_messages, num_input_tokens = truncate_messages(messages, system_prompt, max_tokens=max_input_token)
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
                
        # 응답 생성 완료
        st.session_state.generating_response = False

    except Exception as e:
        # 재시도 불가능한 명확한 오류들
        error_str = str(e)
        if ('overloaded_error' in error_str or 
            'rate_limit' in error_str or 
            'authentication' in error_str or
            'permission' in error_str):
            if 'overloaded_error' in error_str:
                st.error("이런, Anthropic 서버가 죽어있네요😞 잠시 후 다시 시도하거나 다른 모델을 사용해 주세요")
            else:
                st.error(f"오류가 발생했습니다: {str(e)}")
            st.session_state.generating_response = False
        else:
            # 재시도 가능한 오류 - 플래그 유지하고 조용히 실패
            # 상위에서 재검증 로직이 재시도할 것임
            pass
        
