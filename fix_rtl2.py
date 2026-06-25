"""Fix rtl_codegen.py - remove duplicates, fix indent, add missing methods."""
p = r'compiler\codegen\rtl_codegen.py'
with open(p, 'r', encoding='utf8') as f:
    c = f.read()

# 1. Remove duplicate methods
def remove_dup(text, method_name):
    idx1 = text.find(method_name)
    idx2 = text.find(method_name, idx1 + 50)
    if idx2 > 0:
        next_def = text.find('\n    def ', idx2)
        text = text[:idx2] + text[next_def:]
        print(f'Removed duplicate {method_name}')
    return text

c = remove_dup(c, '_collect_external_refs')
c = remove_dup(c, '_gen_function_module')

# 2. Fix generate() indentation
old_bug = '''            for proc in model.processes:
                if proc.name == "forward":
                    files[f"v_output/behavior/m_forward.v"] = self._gen_pipeline_module(proc)
                else:
                    safe = self._sanitize_module_name(f"m_{proc.name}")
                files[f"v_output/behavior/{safe}.v"] = self._gen_process_module(proc)'''

new_fix = '''            for proc in model.processes:
                if proc.name == "forward":
                    files[f"v_output/behavior/m_forward.v"] = self._gen_pipeline_module(proc)
                else:
                    safe = self._sanitize_module_name(f"m_{proc.name}")
                    files[f"v_output/behavior/{safe}.v"] = self._gen_process_module(proc)'''

c = c.replace(old_bug, new_fix)
print('Fixed generate() indent')

# 3. Add _collect_rtl_regs if missing
if '_collect_rtl_regs' not in c:
    marker = '    def _gen_function_module(self, func: FunctionDef) -> str:'
    add = '''    def _collect_rtl_regs(self, stmt):
        """递归收集VarDeclStmt变量，返回reg声明列表。"""
        decls = []
        if stmt is None:
            return decls
        if isinstance(stmt, VarDeclStmt):
            w = 32
            if stmt.var_type and isinstance(stmt.var_type, BitVectorType):
                w = stmt.var_type.width
            decls.append(f"reg [{w-1}:0] {stmt.name};")
        elif isinstance(stmt, CompoundStmt):
            for s in stmt.stmts:
                decls.extend(self._collect_rtl_regs(s))
        elif isinstance(stmt, IfStmt):
            decls.extend(self._collect_rtl_regs(stmt.then_stmt))
            decls.extend(self._collect_rtl_regs(stmt.else_stmt))
        elif isinstance(stmt, (WhileStmt, ForStmt)):
            decls.extend(self._collect_rtl_regs(stmt.body))
        elif isinstance(stmt, SwitchStmt):
            for cs in stmt.cases:
                decls.extend(self._collect_rtl_regs(cs.stmt))
        return decls

''' + marker
    c = c.replace(marker, add)
    print('Added _collect_rtl_regs')

with open(p, 'w', encoding='utf8') as f:
    f.write(c)
print('Done! All fixes applied.')
