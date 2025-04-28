import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 페이지 제목 설정
st.title('Streamlit 테스트 웹페이지')
st.subheader('기본 기능 데모')

# 사이드바 구성
st.sidebar.header('설정')
user_name = st.sidebar.text_input('이름을 입력하세요')
age = st.sidebar.slider('나이', 0, 100, 25)
favorite_color = st.sidebar.selectbox(
    '좋아하는 색상',
    ['빨강', '파랑', '초록', '노랑', '보라']
)

# 사용자 입력 표시
if user_name:
    st.write(f'안녕하세요, {user_name}님! {age}세이시네요.')
    st.write(f'좋아하는 색상: {favorite_color}')

# 구분선
st.markdown('---')

# 탭 생성
tab1, tab2, tab3 = st.tabs(['📈 차트', '🗃 데이터', '🧮 계산기'])

with tab1:
    st.header('차트 예시')
    
    # 데이터 생성
    chart_data = pd.DataFrame(
        np.random.randn(20, 3),
        columns=['A', 'B', 'C']
    )
    
    # 차트 종류 선택
    chart_type = st.radio(
        "차트 유형 선택",
        ('라인 차트', '바 차트', '영역 차트')
    )
    
    if chart_type == '라인 차트':
        st.line_chart(chart_data)
    elif chart_type == '바 차트':
        st.bar_chart(chart_data)
    else:
        st.area_chart(chart_data)
        
    # matplotlib 사용 예시
    st.subheader('Matplotlib 시각화')
    fig, ax = plt.subplots()
    ax.scatter(chart_data['A'], chart_data['B'], alpha=0.5)
    ax.set_xlabel('A 값')
    ax.set_ylabel('B 값')
    st.pyplot(fig)

with tab2:
    st.header('데이터 테이블')
    
    # 샘플 데이터프레임 생성
    df = pd.DataFrame({
        '이름': ['김철수', '이영희', '박지민', '최수진', '정민준'],
        '나이': [22, 35, 28, 42, 31],
        '직업': ['학생', '개발자', '디자이너', '교사', '연구원'],
        '점수': [85, 92, 78, 96, 88]
    })
    
    # 데이터 표시
    st.dataframe(df)
    
    # 데이터 필터링
    min_score = st.slider('최소 점수 필터', 0, 100, 75)
    filtered_df = df[df['점수'] >= min_score]
    st.write(f'점수가 {min_score} 이상인 사람들:')
    st.dataframe(filtered_df)
    
    # CSV 다운로드 버튼
    st.download_button(
        label="CSV로 다운로드",
        data=filtered_df.to_csv(index=False).encode('utf-8'),
        file_name='filtered_data.csv',
        mime='text/csv',
    )

with tab3:
    st.header('간단한 계산기')
    
    col1, col2 = st.columns(2)
    
    with col1:
        num1 = st.number_input('첫 번째 숫자', value=0.0)
    
    with col2:
        num2 = st.number_input('두 번째 숫자', value=0.0)
    
    operation = st.selectbox(
        '연산 선택',
        ('더하기', '빼기', '곱하기', '나누기')
    )
    
    if st.button('계산하기'):
        if operation == '더하기':
            result = num1 + num2
            st.success(f'결과: {num1} + {num2} = {result}')
        elif operation == '빼기':
            result = num1 - num2
            st.success(f'결과: {num1} - {num2} = {result}')
        elif operation == '곱하기':
            result = num1 * num2
            st.success(f'결과: {num1} × {num2} = {result}')
        elif operation == '나누기':
            if num2 == 0:
                st.error('0으로 나눌 수 없습니다!')
            else:
                result = num1 / num2
                st.success(f'결과: {num1} ÷ {num2} = {result}')

# 파일 업로드 예시
st.markdown('---')
st.header('파일 업로드 테스트')
uploaded_file = st.file_uploader("CSV 파일을 업로드하세요", type=['csv'])

if uploaded_file is not None:
    try:
        # 파일 읽기
        df_upload = pd.read_csv(uploaded_file)
        st.write('업로드된 데이터:')
        st.dataframe(df_upload)
        
        # 데이터 요약 통계
        st.write('데이터 요약:')
        st.write(df_upload.describe())
        
    except Exception as e:
        st.error(f'오류 발생: {e}')

# 맨 아래 상태표시줄
st.markdown('---')
st.caption('Streamlit 테스트 애플리케이션 v1.0')
