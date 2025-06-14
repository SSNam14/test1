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
    # 메시지 기록 준비
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
    ]
    truncated_messages, num_input_tokens = truncate_messages(messages, system_prompt, max_tokens=max_input_token)
    st.session_state.num_input_tokens = num_input_tokens
    
    # 응답 관련 변수들을 미리 초기화
    full_response = ""
    response_placeholder = None
    
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
                
                # 응답 스트리밍 (더 안전한 처리)
                try:
                    for text in claude_stream_generator(response):
                        full_response += text
                        # 응답 업데이트 (예외 처리 추가)
                        try:
                            response_placeholder.markdown(full_response)
                        except Exception as display_error:
                            # 화면 업데이트 실패해도 계속 진행
                            print(f"Display update failed: {display_error}")
                            continue
                            
                except Exception as stream_error:
                    print(f"Streaming error: {stream_error}")
                    # 스트리밍이 중단되어도 지금까지 받은 응답은 저장
                    if full_response.strip():
                        st.warning("응답 중 연결이 끊어졌지만, 부분 응답을 저장합니다.")
                    else:
                        raise stream_error  # 아무것도 받지 못했으면 예외 발생
                
                # 최종 응답 표시
                if response_placeholder and full_response:
                    response_placeholder.markdown(full_response)
            
            # 메시지 기록에 추가 (응답이 있을 때만)
            if full_response.strip():
                st.session_state.messages.append({"role": "assistant", "content": full_response})
                print(f"Response saved to history: {len(full_response)} characters")
            else:
                st.error("빈 응답을 받았습니다. 다시 시도해주세요.")
                
        # 응답 생성 완료
        st.session_state.generating_response = False
        
    except Exception as e:
        # 예외 발생 시에도 부분 응답이 있으면 저장
        if full_response.strip():
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            st.warning(f"오류가 발생했지만 부분 응답을 저장했습니다: {str(e)}")
        else:
            # 응답이 없으면 기존 오류 처리
            if 'overloaded_error' in str(e):
                st.error("이런, Anthropic 서버가 죽어있네요😞 잠시 후 다시 시도하거나 다른 모델을 사용해 주세요")
            else:
                st.error(f"오류가 발생했습니다: {str(e)}")
        
        st.session_state.generating_response = False
        
        # 디버깅을 위한 로그
        print(f"Exception in generate_claude_response: {str(e)}")
        print(f"Full response at exception: '{full_response}'")        
