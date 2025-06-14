import re


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

    #괄호로만 이루어진 줄은 코드의 일부일 가능성 높음
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
            not any(stripped.startswith(op) for op in ['if ', 'for ', 'while ', 'def ', 'class ']) and
            not bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_\.]*\s*\(", stripped))):
            return False
        return True
    
    return False

def render_mixed_content(content: str) -> str:
    lines = content.splitlines()
    current_block = []
    current_type = None  # "code" or "text"
    result_parts = []
    
    def flush():
        nonlocal current_block, current_type
        if not current_block:
            return
        text = "\n".join(current_block)
        if current_type == "code":
            text = escape_literal_newlines_fixed(text)
            result_parts.append(f"```python\n{text}\n```")
        else:
            result_parts.append(text)
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
    
    # 결과를 하나의 문자열로 합치기
    return "\n".join(result_parts)
