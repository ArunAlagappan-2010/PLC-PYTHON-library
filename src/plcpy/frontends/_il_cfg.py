"""Raise IL jump+label patterns back into structured IR (If / While).

Recognises two exact shapes; anything else is left as flat Label/Jump (still
executable via the Python backend's goto interpreter):

  if-then:  JMPCN L ; <plain stmts...> ; L:        ->  If(cond, then=<stmts>)
  while:    G: ; JMPCN END ; <body...> ; JMP G ; END:  ->  While(cond, body)
"""
from __future__ import annotations
from .. import ir


def raise_structured(body: list[ir.Stmt]) -> list[ir.Stmt]:
    out: list[ir.Stmt] = []
    i = 0
    n = len(body)
    while i < n:
        s = body[i]

        # while:  G: ; JMPCN END ; body... ; JMP G ; END:
        if isinstance(s, ir.Label):
            guard = s.name
            if (i + 1 < n and isinstance(body[i + 1], ir.Jump)
                    and body[i + 1].cond is not None and body[i + 1].negate):
                end = body[i + 1].target
                cond = body[i + 1].cond
                j = i + 2
                block: list[ir.Stmt] = []
                ok = True
                while j < n:
                    bj = body[j]
                    if (isinstance(bj, ir.Jump) and bj.cond is None
                            and bj.target == guard):
                        break
                    if isinstance(bj, (ir.Jump, ir.Label)):
                        ok = False
                        break
                    block.append(bj)
                    j += 1
                # after the back-jump must come Label(end)
                if (ok and j + 1 < n and isinstance(body[j], ir.Jump)
                        and isinstance(body[j + 1], ir.Label)
                        and body[j + 1].name == end):
                    out.append(ir.While(cond, block))
                    i = j + 2
                    continue

        # if-then:  JMPCN L ; stmts... ; L:
        if isinstance(s, ir.Jump) and s.cond is not None and s.negate:
            label = s.target
            j = i + 1
            block = []
            ok = True
            while j < n and not (isinstance(body[j], ir.Label) and body[j].name == label):
                if isinstance(body[j], (ir.Jump, ir.Label)):
                    ok = False
                    break
                block.append(body[j])
                j += 1
            if ok and j < n:
                out.append(ir.If(s.cond, block, [], []))
                i = j + 1
                continue

        out.append(s)
        i += 1
    return out
