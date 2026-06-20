PROGRAM Delay
VAR_INPUT
 trig : BOOL;
END_VAR
VAR_OUTPUT
 out : BOOL;
END_VAR
VAR
 t : TON;
END_VAR
 t(IN := trig, PT := T#500ms);
 out := t.Q;
END_PROGRAM
