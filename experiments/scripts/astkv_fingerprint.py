"""
astkv_fingerprint.py
--------------------
AST 서브트리 추출 -> α-rename 정규화 -> BLAKE3 지문.
ast-kv 프로젝트 task용 정식 모듈 (test용 ast_fingerprint.py 대체).
"""

import blake3
import tree_sitter_python as tspython
from tree_sitter import Language, Parser
from transformers import AutoTokenizer

PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)

ALLOWED_TYPES = {
    "function_definition",
    "class_definition",
    "import_statement",
    "import_from_statement",
    "call",
    "assignment",
}

_TOKENIZER = None
_TOKENIZER_PATH = None


def init_tokenizer(path):
    """Qwen 토크나이저를 1회 로딩. min_tokens 필터에 사용."""
    global _TOKENIZER, _TOKENIZER_PATH
    _TOKENIZER = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
    _TOKENIZER_PATH = path
    return _TOKENIZER


def count_tokens(text):
    """주어진 텍스트의 실제 모델 토큰 수."""
    if _TOKENIZER is None:
        raise RuntimeError("init_tokenizer()를 먼저 호출하세요.")
    return len(_TOKENIZER.encode(text, add_special_tokens=False))


def extract_subtrees(root, code_bytes, min_depth=2, min_tokens=8):
    """
    자격 조건(깊이>=2, 토큰수>=min_tokens, 허용 노드)을 갖춘
    '최상위' 서브트리만 반환. 자격 노드를 찾으면 그 안으로는 재귀하지 않는다.
    """
    results = []

    def get_depth(n):
        if not n.children:
            return 0
        return 1 + max(get_depth(c) for c in n.children)

    def traverse(n):
        if n.type in ALLOWED_TYPES:
            depth = get_depth(n)
            if depth >= min_depth:
                text = code_bytes[n.start_byte:n.end_byte].decode("utf-8", "ignore")
                if count_tokens(text) >= min_tokens:
                    results.append(n)
                    return  # 자격 노드 -> 자식으로 안 내려감 (최상위만)
        for child in n.children:
            traverse(child)

    traverse(root)
    return results


def _field_of(node):
    """node 가 부모에서 갖는 field 이름. 없으면 None.
    child_by_field_name 이 새 wrapper를 반환해 'is' 비교가 깨지므로
    부모 자식 리스트에서 바이트 범위로 동일 노드를 찾아 field_name_for_child 로 조회."""
    parent = node.parent
    if parent is None:
        return None
    for i, c in enumerate(parent.children):
        if c.start_byte == node.start_byte and c.end_byte == node.end_byte \
                and c.type == node.type:
            return parent.field_name_for_child(i)
    return None


def _is_variable_identifier(node):
    """
    identifier 가 지역 변수/파라미터(=치환 대상)인지 휴리스틱 판정.
    보존(False): function/class def name, call function, attribute의 object/attribute,
                 keyword_argument name, import 계열 내부 식별자.
    한계: attribute.object 일괄 보존 -> 진짜 변수의 메서드 호출(obj.method의 obj)도 보존됨.
    """
    parent = node.parent
    if parent is None:
        return True

    ptype = parent.type

    cur = parent #import 내부 식별자 보존
    while cur is not None:
        if cur.type in ("import_statement", "import_from_statement"):
            return False
        cur = cur.parent

    field = _field_of(node)
    
    #함수/클래스명 보존
    if ptype in ("function_definition", "class_definition") and field == "name":
        return False
    #호출 대상 함수명 보존
    if ptype == "call" and field == "function":
        return False
    #모듈명/메서드명/속성명 보존
    if ptype == "attribute" and field in ("attribute", "object"):
        return False
    #keyword argument 이름 보존 e.g.(foo(key=val)에서 key)
    if ptype == "keyword_argument" and field == "name":
        return False

    return True


def normalize(node, code_bytes, rename_mode="vars_only"):
    """
    서브트리 -> 정규화된 S-expression 문자열.
    rename_mode: 'vars_only' | 'all'
    리터럴(string/integer/float)은 STR/NUM 으로 표준화.
    """
    var_map = {}
    counter = [0]

    def rename_id(name):
        if name not in var_map:
            var_map[name] = f"VAR_{counter[0]}"
            counter[0] += 1
        return var_map[name]

    def walk(n):
        t = n.type

        if t == "string":
            return "STR"
        if t in ("integer", "float"):
            return "NUM"
        if t in ("true", "false", "none"):
            return t.upper()

        if t == "identifier":
            name = code_bytes[n.start_byte:n.end_byte].decode("utf-8", "ignore")
            if rename_mode == "all":
                return rename_id(name)
            if _is_variable_identifier(n):
                return rename_id(name)
            return name

        if not n.children:
            return code_bytes[n.start_byte:n.end_byte].decode("utf-8", "ignore")

        inner = " ".join(walk(c) for c in n.children)
        return f"({t} {inner})"

    return walk(node)


def fingerprint(node, code_bytes, rename_mode="vars_only"):
    """서브트리 -> BLAKE3 32바이트 지문 (hexdigest)."""
    norm = normalize(node, code_bytes, rename_mode=rename_mode)
    return blake3.blake3(norm.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    import sys, os

    tok_path = sys.argv[1] if len(sys.argv) > 1 else \
        "~/local-proj/ast-kv/models/Qwen3-Coder-30B-A3B-Instruct"
    init_tokenizer(os.path.expanduser(tok_path))

    code = '''
def parse_json(s):
    return json.loads(s)

def parse_data(payload):
    return json.loads(payload)

def parse_pickle(payload):
    return pickle.loads(payload)
'''
    cb = code.encode("utf-8")
    tree = parser.parse(cb)
    subs = extract_subtrees(tree.root_node, cb, min_tokens=8)
    print(f"최상위 자격 서브트리: {len(subs)}개\n")
    for i, n in enumerate(subs):
        txt = cb[n.start_byte:n.end_byte].decode("utf-8")
        print(f"[{i+1}] {n.type}  ({count_tokens(txt)} tokens)")
        for mode in ("vars_only", "all"):
            print(f"    {mode:10s}: {fingerprint(n, cb, mode)[:16]}  | {normalize(n, cb, mode)[:70]}")
        print()
    print("기대: parse_json/parse_data 는 vars_only에서 같은 지문 (변수명만 다름),")
    print("      parse_pickle 은 다른 지문 (json vs pickle 보존됨).")
    print("      all 모드에서는 셋 다 같은 지문.")
