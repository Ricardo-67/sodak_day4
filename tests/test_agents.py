from app.agents import run_specialist, SupervisorTools
from app.providers import ScriptedProvider, ModelTurn, ToolCall
from app.tools.hostel_tools import InformationTools, DeskTools

def test_supervisor_delegation(db):
    provs = {
        "information": ScriptedProvider([ModelTurn(text="info reply")]),
        "desk": ScriptedProvider([ModelTurn(text="desk reply")]),
    }
    sup = SupervisorTools(db, provs, "22CS045")
    
    res = sup.delegate("ask_information", {"question": "q"}, "k1")
    assert res["answer"] == "info reply"
    
    res = sup.delegate("ask_desk", {"request": "r"}, "k2")
    assert res["answer"] == "desk reply"

def test_specialist_runs_tools(db):
    prov = ScriptedProvider([
        ModelTurn(text=None, tool_calls=[ToolCall("raise_complaint", {"issue": "plumbing"})]),
        ModelTurn(text="done")
    ])
    res = run_specialist("desk", "sys", DeskTools(db, "22CS045"), db=db, provider=prov, task="task", parent_key="key")
    assert res["answer"] == "done"
    assert "raise_complaint" in res["tools_used"]
    assert db.count("complaint") == 2 # seed has 1

def test_specialist_step_limit(db):
    prov = ScriptedProvider([], loop=True) # returns script exhausted since it has no tool calls
    prov = ScriptedProvider([ModelTurn(text=None, tool_calls=[ToolCall("get_student", {})])], loop=True)
    res = run_specialist("desk", "sys", DeskTools(db, "22CS045"), db=db, provider=prov, task="task", parent_key="key")
    assert "error" in res
    assert res["error"] == "specialist_step_limit"
