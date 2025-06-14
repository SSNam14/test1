import extra_streamlit_components as stx
import streamlit as st
import datetime
import time

# 페이지 설정 및 쿠키 컨트롤러 초기화
def initialize_cookie(cookie_manager, COOKIE_KEY):
    if 'cookie_initialized' not in st.session_state:
        try:
            user_cookie = cookie_manager.get(COOKIE_KEY)
            time.sleep(1)
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
def authenticate_user(db, email):
    if not email or not email.strip(): # 빈 이메일 체크
        return None

    email = email.lower().strip()
    user_doc = db.collection('users').document(email).get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        return user_data.get('name')
    return None

def login(db, cookie_manager, COOKIE_KEY):
    email = st.session_state.email_input

    if not email or not email.strip():
        st.session_state.login_error = True
        st.session_state.error_message = "이메일을 입력해주세요."
        return

    user_name = authenticate_user(db, email)

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
            time.sleep(1)
            print("쿠키 설정 완료")
        except Exception as e:
            print(f"쿠키 설정 실패: {e}")

    else:
        st.session_state.login_error = True
        st.session_state.error_message = "등록되지 않은 이메일입니다."

def logout(cookie_manager, COOKIE_KEY):
    st.session_state.user_email = None
    st.session_state.user_name = None
    st.session_state.email_input = ""
    try:
        cookie_manager.delete(COOKIE_KEY)
        time.sleep(1)
        print("쿠키 삭제 완료")
    except Exception as e:
        print(f"쿠키 삭제 실패: {e}")
    st.rerun()
