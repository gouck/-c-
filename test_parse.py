"""Test script: lex + parse 8mSpec_0821.c end-to-end."""
import sys
sys.path.insert(0, '.')

from compiler.lexer.pseudoc_lexer import PseudoCLexer
from compiler.parser.pseudoc_parser import PseudoCParser

def main():
    path = r'source/8mSpec_0821.c'
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()

    lexer = PseudoCLexer(source)
    tokens = lexer.tokenize()

    # 过滤掉 NEWLINE，只看有效 token
    real_tokens = [t for t in tokens if t.type.name != 'NEWLINE']
    print(f"Token 总数: {len(tokens)}（含换行 {len(tokens) - len(real_tokens)} 个）")
    print(f"前 20 个 Token:")
    for t in real_tokens[:20]:
        print(f"  {t.type.name:20s} '{t.value}'  L{t.line}:{t.column}")
    print("...")

    print(f"\n开始语法分析...")
    parser = PseudoCParser(real_tokens)
    try:
        model = parser.parse()
        print(f"解析成功！")
        print(f"  Processes: {len(model.processes)}")
        for p in model.processes:
            print(f"    - {p.name}")
        print(f"  Functions: {len(model.functions)}")
        for f in model.functions:
            print(f"    - {f.name}")
    except Exception as e:
        print(f"解析失败: {e}")

if __name__ == '__main__':
    main()
