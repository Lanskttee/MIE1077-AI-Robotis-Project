"""Tests for the Phase-3 IoT additions (thermostat, TV, speaker, fan, lock)."""

from __future__ import annotations

from homemate.world.iot import (
    CoffeeMaker,
    Curtain,
    DoorLock,
    Fan,
    IoTNetwork,
    Lamp,
    Speaker,
    Thermostat,
    Toaster,
    TV,
)


def test_default_network_has_eleven_devices_across_all_rooms() -> None:
    net = IoTNetwork.default()
    devs = net.list()
    assert len(devs) == 11
    rooms = {d.room for d in devs}
    assert rooms == {"living_room", "bedroom", "kitchen"}
    # device kind coverage
    kinds = {d.kind for d in devs}
    assert kinds == {
        "curtain", "lamp", "toaster", "coffee_maker",
        "thermostat", "tv", "speaker", "fan", "door_lock",
    }


def test_thermostat_set_target_clamps_and_remembers_mode() -> None:
    t = Thermostat("thermostat.living_room", "living_room")
    assert t.apply("set_target", target_c=22)["ok"] is True
    assert t.state["target_c"] == 22.0
    # clamp high and low
    t.apply("set_target", target_c=99)
    assert t.state["target_c"] == 32.0
    t.apply("set_target", target_c=-99)
    assert t.state["target_c"] == 10.0
    # mode transitions
    t.apply("off")
    assert t.state["mode"] == "off"
    t.apply("set_mode", mode="heat")
    assert t.state["mode"] == "heat"
    err = t.apply("set_mode", mode="boost")
    assert err["ok"] is False


def test_thermostat_tick_drifts_current_toward_target() -> None:
    t = Thermostat("thermostat.living_room", "living_room")
    t.apply("set_target", target_c=25)
    start = t.state["current_c"]
    t.tick(2.0)
    assert t.state["current_c"] > start
    assert t.state["current_c"] <= 25.0


def test_tv_channel_validation_and_set_channel_implies_on() -> None:
    tv = TV("tv.living_room", "living_room")
    err = tv.apply("set_channel", channel="weather")
    assert err["ok"] is False and "available" in err
    res = tv.apply("set_channel", channel="news")
    assert res["ok"] is True
    assert tv.state["channel"] == "news"
    assert tv.state["on"] is True


def test_tv_volume_clamps_to_unit_interval() -> None:
    tv = TV("tv.living_room", "living_room")
    tv.apply("set_volume", volume=1.5)
    assert tv.state["volume"] == 1.0
    tv.apply("set_volume", volume=-0.5)
    assert tv.state["volume"] == 0.0


def test_speaker_play_with_playlist_starts_playback() -> None:
    sp = Speaker("speaker.bedroom", "bedroom")
    res = sp.apply("play", playlist="jazz")
    assert res["ok"] is True
    assert sp.state["playing"] is True
    assert sp.state["playlist"] == "jazz"
    err = sp.apply("play", playlist="grunge")
    assert err["ok"] is False


def test_fan_set_speed_clamps_and_turns_on() -> None:
    f = Fan("fan.bedroom", "bedroom")
    f.apply("set_speed", speed=5)
    assert f.state["speed"] == 3 and f.state["on"] is True
    f.apply("set_speed", speed=0)
    assert f.state["speed"] == 1
    f.apply("off")
    assert f.state["on"] is False


def test_door_lock_toggle_round_trip() -> None:
    lock = DoorLock("lock.front_door", "living_room")
    assert lock.state["locked"] is True
    lock.apply("unlock")
    assert lock.state["locked"] is False
    lock.apply("toggle")
    assert lock.state["locked"] is True


def test_network_act_rejects_unknown_action() -> None:
    net = IoTNetwork.default()
    err = net.act("thermostat.living_room", "fly")
    assert err["ok"] is False
    assert "available" in err


def test_network_tick_advances_thermostat_and_toaster() -> None:
    net = IoTNetwork.default()
    net.act("thermostat.living_room", "set_target", target_c=25)
    net.act("toaster.kitchen", "start", level=3)
    net.tick(1.0)
    therm = net.get("thermostat.living_room").state
    toast = net.get("toaster.kitchen").state
    assert therm["current_c"] > 21.0
    assert toast["progress"] > 0
