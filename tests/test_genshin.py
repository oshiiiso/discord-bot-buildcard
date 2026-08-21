"""スコアとビルドカードの回帰テスト。"""

from games.base import ParsedPiece, ParsedStat
from games.genshin import GenshinGame
from games.genshin.suitability import judge_suitability


def _sample_flower() -> ParsedPiece:
    return ParsedPiece(
        slot="flower",
        set_id="gladiator",
        set_name_ja="剣闘士のフィナーレ",
        main=ParsedStat(key="hp_flat", value=4780, is_percent=False),
        subs=[
            ParsedStat(key="crit_rate", value=3.9, is_percent=True),
            ParsedStat(key="crit_dmg", value=7.8, is_percent=True),
            ParsedStat(key="atk_pct", value=5.8, is_percent=True),
            ParsedStat(key="er", value=6.5, is_percent=True),
        ],
    )


def test_atk_score_formula() -> None:
    game = GenshinGame()
    piece = _sample_flower()
    preset = next(p for p in game.generic_presets() if p.id == "atk")
    result = game.score(piece, preset)
    assert result.total == 21.4


def test_suitability_standard_on_flower() -> None:
    game = GenshinGame()
    piece = _sample_flower()
    hutao = game.get_character("hutao")
    assert hutao is not None
    build = hutao.builds[0]
    suit = judge_suitability(piece, build)
    assert suit.main_mark == "preferred"


def test_messages_load() -> None:
    import messages as msg
    from services.copy import t

    assert msg.MSG_01 == "カードを出す"
    assert "UID" in t(msg.ERR_15)
    assert msg.MSG_RANK["godly"] == "SS"
    assert "Enka" not in msg.MSG_08
    assert "Enka" not in msg.MSG_30
    assert "Enka" not in msg.MSG_49
    assert "Enka" not in msg.ERR_12


def test_start_view_persistent() -> None:
    from config import START_BUTTON_CUSTOM_ID
    from ui.start_view import StartCardView

    view = StartCardView()
    assert view.timeout is None
    assert any(getattr(item, "custom_id", None) == START_BUTTON_CUSTOM_ID for item in view.children)


def test_latest_characters_and_sets() -> None:
    game = GenshinGame()
    assert game.resolve_character("マーヴィカ") is not None
    assert game.resolve_character("コロンビーナ") is not None
    assert game.resolve_character("オデット") is not None
    assert game.find_set("月を紡ぐ夜の歌") == "silken_moon"
    assert game.find_set("長き夜の誓い") == "long_night"
    assert game.find_set("紅血の証") == "crimson_oath"
    assert game.find_set("黒曜の秘典") == "obsidian"
    assert game.character_by_enka_key("10000106") is not None
    assert game.character_by_enka_key("10000125") is not None


def test_fallback_character_uses_generic_builds() -> None:
    game = GenshinGame()
    character = game.fallback_character(10000999, "テスト", "pyro")
    assert character.name_ja == "テスト"
    assert {b.id for b in character.builds} >= {"atk", "hp", "def", "em", "er"}


def test_extra_character_uses_scale() -> None:
    from games.genshin.catalog import extra_character_to_info, valid_set_id

    info = extra_character_to_info(
        {
            "enka_id": "10000999",
            "name_ja": "テスト",
            "element": "geo",
            "scale": "def",
            "aliases": ["Testo"],
        }
    )
    assert info.id == "testo"
    assert info.enka_keys == ["10000999"]
    assert info.builds[0].id == "def"
    assert info.builds[0].weights["def_pct"] == 1.0
    assert valid_set_id("crimson_oath")
    assert not valid_set_id("紅血")
    assert not valid_set_id("1bad")


def test_chiori_portrait_names() -> None:
    from services.enka_client import EnkaClient

    client = EnkaClient()
    client._store = {
        "10000094-10941": {"Element": "Rock"},
        "10000094": {"SideIconName": "UI_AvatarIcon_Side_Chiori"},
    }
    names = client.portrait_names(10000094, 10941, None)
    assert names[0] == "UI_Gacha_AvatarImg_Chiori"
    assert "UI_Gacha_AvatarIcon_Chiori" in names
    assert "UI_AvatarIcon_Chiori" in names
    assert client._icon_for_avatar(10000094, 10941, None) == "UI_AvatarIcon_Chiori"


def test_chiori_portrait_names_without_store() -> None:
    from services.enka_client import EnkaClient

    client = EnkaClient()
    client._store = {}
    names = client.portrait_names(10000094, 0, None)
    assert "UI_Gacha_AvatarIcon_Chiori" in names
    assert "UI_AvatarIcon_Chiori" in names


def test_zibai_portrait_names() -> None:
    from services.enka_client import EnkaClient

    client = EnkaClient()
    client._store = {}
    names = client.portrait_names(10000126, 0, None)
    assert "UI_Gacha_AvatarIcon_Zibai" in names
    assert "UI_AvatarIcon_Zibai" in names


def test_zibai_skills_without_store() -> None:
    from services.enka_client import EnkaClient

    client = EnkaClient()
    skills = client._skills_for_avatar({}, {"12631": 8, "12632": 6, "12635": 7}, "Zibai")
    assert skills == [
        ("Skill_A_01", 8),
        ("Skill_S_Zibai_01", 6),
        ("Skill_E_Zibai_01", 7),
    ]
    consts = client._const_icons({}, "Zibai")
    assert consts[0] == "UI_Talent_S_Zibai_01"
    assert len(consts) == 6


def test_fit_portrait_keeps_tall_art() -> None:
    from PIL import Image
    from services.card_renderer import _fit_portrait

    src = Image.new("RGBA", (100, 400), (0, 0, 0, 0))
    src.paste(Image.new("RGBA", (80, 380), (255, 0, 0, 255)), (10, 10))
    out = _fit_portrait(src, (200, 220))
    assert out.size == (200, 220)
    assert out.getpixel((0, 110))[3] < 16
    assert out.getpixel((199, 110))[3] < 16


def test_render_card_smoke() -> None:
    from services.card_renderer import render_build_card
    from services.enka_client import EnkaAvatar, EnkaShowcase

    game = GenshinGame()
    hutao = game.get_character("hutao")
    assert hutao is not None
    piece = _sample_flower()
    avatar = EnkaAvatar(
        avatar_id=10000046,
        skill_depot_id=0,
        name_ja=hutao.name_ja,
        icon="",
        level=90,
        constellations=6,
        friendship=10,
        character=hutao,
        pieces=[piece],
        weapon=None,
        stats={"hp": 30000, "atk": 2000, "def": 800, "em": 100, "er": 120, "crit_rate": 80, "crit_dmg": 200},
        element="pyro",
    )
    png = render_build_card(
        EnkaShowcase(uid="1", nickname="tester", level=60, avatars=[avatar], ttl=60),
        avatar,
        hutao.builds[0],
        portrait_bytes=None,
        weapon_bytes=None,
    )
    assert png.startswith(b"\x89PNG")


def test_uid_pick_has_refresh() -> None:
    import messages as msg
    from services.copy import t
    from services.session_store import SessionStore, UidSession
    from ui.uid_view import UidPickView

    class _Cog:
        def __init__(self) -> None:
            self.sessions = SessionStore()

    cog = _Cog()
    cog.sessions.put(1, UidSession(user_id=1, uid="123456789", nickname="t", avatars=[]))
    view = UidPickView(cog, 1)  # type: ignore[arg-type]
    labels = [getattr(item, "label", None) for item in view.children]
    assert t(msg.MSG_55) in labels


def test_all_characters_have_portrait_and_build() -> None:
    from services.character_check import collect_rows, problem_rows
    from services.enka_client import EnkaClient

    client = EnkaClient()
    client._store = {}
    rows = collect_rows(client)
    assert rows
    assert problem_rows(rows) == []


def test_cleanup_enka_assets_drops_old_and_empty(tmp_path) -> None:
    import os
    import time

    from services.enka_client import cleanup_enka_assets

    keep = tmp_path / "keep.png"
    old = tmp_path / "old.png"
    empty = tmp_path / "empty.png"
    keep.write_bytes(b"abc")
    old.write_bytes(b"abc")
    empty.write_bytes(b"")
    now = time.time()
    os.utime(old, (now - 40 * 86400, now - 40 * 86400))
    assert cleanup_enka_assets(tmp_path, 30, now=now) == 2
    assert keep.exists()
    assert not old.exists()
    assert not empty.exists()


def test_cleanup_enka_assets_skips_when_disabled(tmp_path) -> None:
    from services.enka_client import cleanup_enka_assets

    path = tmp_path / "keep.png"
    path.write_bytes(b"abc")
    assert cleanup_enka_assets(tmp_path, 0) == 0
    assert path.exists()
