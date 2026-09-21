import datetime
from app.tools.hostel_tools import InformationTools, DeskTools

def test_information_tools(db):
    info = InformationTools(db)
    
    res = info.get_room("A", "101")
    assert res["room_id"] == 1
    
    res = info.find_complaint("A", "101")
    assert len(res["complaints"]) == 1
    assert res["complaints"][0]["issue"] == "electrical"

def test_desk_tools_can_raise(db):
    desk = DeskTools(db, "22CS045")
    assert desk.check_can_raise()["can_raise"] is True

    desk_warned = DeskTools(db, "22IT017")
    assert desk_warned.check_can_raise()["can_raise"] is False

def test_desk_tools_raise_complaint(db):
    desk = DeskTools(db, "22CS045")
    res = desk.raise_complaint("plumbing")
    assert res["status"] == "raised"
    
    # Second time for the same issue in the same room should be already_raised
    res2 = desk.raise_complaint("plumbing")
    assert res2["status"] == "already_raised"

def test_desk_tools_notify(db, clock):
    desk = DeskTools(db, "22CS045", clock=lambda: datetime.datetime(2026, 9, 21, tzinfo=datetime.timezone.utc))
    res = desk.notify_student("Test")
    assert res["status"] == "queued"
    assert res["duplicate"] is False
    
    res2 = desk.notify_student("Test")
    assert res2["duplicate"] is True
