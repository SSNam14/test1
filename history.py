import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from zoneinfo import ZoneInfo
import json

import chat

# Firebase 초기화
def initialize_firebase():
    if not firebase_admin._apps:
        cred_dict = dict(st.secrets["firebase"])
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        
    return firestore.client()

def save_conversation_as_json():
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
def save_conversation_to_db(db):
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
        print(f"db에 {user_name} 의 대화를 저장합니다.")

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

def load_conversation_from_db(session_id, db):
    if 'user_email' not in st.session_state: 
        user_email = 'anonymous'
        user_name = 'anonymous'
    else:
        user_email = st.session_state.user_email
        user_name = st.session_state.user_name
    print(f"db에서 {user_name} 의 대화를 로드합니다.")

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
            st.query_params['session_id'] = session_id

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

def get_recent_sessions(db, limit=30):
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

from datetime import timezone, timedelta

def group_sessions_by_time(recent_sessions):
    # 사용자의 시간대를 고려하는 것이 가장 좋지만,
    # 여기서는 서버/DB 기준인 UTC로 일관성 있게 처리합니다.
    # 한국 사용자 대상이라면 'Asia/Seoul'로 하는 것도 방법입니다.
    # from zoneinfo import ZoneInfo
    # tz = ZoneInfo("Asia/Seoul")
    # now = datetime.datetime.now(tz)
    
    now = datetime.now(timezone.utc)
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
                dt = datetime.fromtimestamp(timestamp.seconds, tz=timezone.utc)
            elif hasattr(timestamp, 'strftime'):
                dt = timestamp
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            elif isinstance(timestamp, dict) and 'seconds' in timestamp:
                dt = datetime.fromtimestamp(timestamp['seconds'], tz=timezone.utc)
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
        
