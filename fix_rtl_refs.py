# fix_rtl_refs.py
p = r'compiler\codegen\rtl_codegen.py'
with open(p, 'r', encoding='utf8') as f:
    c = f.read()

old = "    def _collect_external_refs(self, stmt, local_names):"
# find the block from this marker to the next method
idx = c.find(old)
if idx < 0:
    print("old method not found!")
    exit(1)
# find next "    def " after this method
next_def = c.find("\n    def ", idx + 100)
if next_def < 0:
    next_def = c.find("\n    @", idx + 100)  # could be staticmethod
if next_def < 0:
    print("next method not found!")
    exit(1)

new_method = """    def _collect_external_refs(self, stmt: "Optional[Stmt]", local: "set[str]") -> "set[str]":
        refs = set()
        if stmt is None:
            return refs
        if isinstance(stmt, VarDeclStmt):
            local.add(stmt.name)
            return refs
        if isinstance(stmt, CompoundStmt):
            for s in stmt.stmts:
                if isinstance(s, VarDeclStmt):
                    local.add(s.name)
            for s in stmt.stmts:
                refs |= self._collect_external_refs(s, local)
            return refs
        if isinstance(stmt, IfStmt):
            refs |= self._expr_has_ref(stmt.cond, local)
            refs |= self._collect_external_refs(stmt.then_stmt, local)
            refs |= self._collect_external_refs(stmt.else_stmt, local)
            return refs
        if isinstance(stmt, WhileStmt):
            refs |= self._expr_has_ref(stmt.cond, local)
            refs |= self._collect_external_refs(stmt.body, local)
            return refs
        if isinstance(stmt, ForStmt):
            refs |= self._expr_has_ref(stmt.cond, local) if stmt.cond else set()
            refs |= self._collect_external_refs(stmt.body, local)
            return refs
        if isinstance(stmt, SwitchStmt):
            refs |= self._expr_has_ref(stmt.expr, local)
            for cs in stmt.cases:
                refs |= self._collect_external_refs(cs.stmt, local)
            return refs
        if isinstance(stmt, AssignStmt):
            refs |= self._expr_has_ref(stmt.lhs, local)
            refs |= self._expr_has_ref(stmt.rhs, local)
            return refs
        if isinstance(stmt, ExprStmt):
            refs |= self._expr_has_ref(stmt.expr, local)
            return refs
        return refs

    def _expr_has_ref(self, expr: "Optional[Expr]", local: "set[str]") -> "set[str]":
        refs = set()
        if expr is None:
            return refs
        if isinstance(expr, IdentifierExpr):
            name = expr.name
            if name not in local and not name.startswith("_") and (not name or not name[0].isdigit()):
                refs.add(name)
            return refs
        if isinstance(expr, BinaryOpExpr):
            return self._expr_has_ref(expr.left, local) | self._expr_has_ref(expr.right, local)
        if isinstance(expr, UnaryOpExpr):
            return self._expr_has_ref(expr.operand, local)
        if isinstance(expr, FieldAccessExpr):
            return self._expr_has_ref(expr.base, local)
        if isinstance(expr, BitSliceExpr):
            return self._expr_has_ref(expr.base, local)
        if isinstance(expr, BitIndexExpr):
            return self._expr_has_ref(expr.base, local) | self._expr_has_ref(expr.index, local)
        if isinstance(expr, FieldIndexExpr):
            r = self._expr_has_ref(expr.base, local)
            if hasattr(expr, 'index') and expr.index:
                r |= self._expr_has_ref(expr.index, local)
            return r
        if isinstance(expr, ConcatExpr):
            r = set()
            for p in expr.parts:
                r |= self._expr_has_ref(p, local)
            return r
        if isinstance(expr, FunctionCallExpr):
            r = set()
            for a in expr.args:
                r |= self._expr_has_ref(a, local)
            return r
        if isinstance(expr, MaxMinExpr):
            r = set()
            for a in expr.args:
                r |= self._expr_has_ref(a, local)
            return r
        return refs

"""

c = c[:idx] + new_method + c[next_def:]
with open(p, 'w', encoding='utf8') as f:
    f.write(c)
print("Fixed! New methods added.")
