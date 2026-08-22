"""UID から紹介キャラのビルドカードを出す。"""

from __future__ import annotations

import asyncio
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands

import messages as msg
from config import CHANNEL_ID
from games.genshin.catalog import parse_aliases, refresh_catalog, upsert_character, upsert_set, valid_set_id
from logging_config import get_logger
from services.card_renderer import render_build_card
from services.channels import is_bot_channel
from services.character_check import collect_rows, format_report, note_rows, problem_rows
from services.copy import t
from services.enka_client import EnkaClient, EnkaError, EnkaShowcase
from services.session_store import SessionStore, UidSession
from ui.guide_embed import formula_embed, guide_embed, is_guide_message
from ui.start_view import CardMessageView, StartCardView
from ui.uid_view import UidPickView

logger = get_logger(__name__)


class BuildCog(commands.Cog):
    """UID からビルドカード。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sessions = SessionStore()
        self.enka = EnkaClient()

    async def cog_load(self) -> None:
        self.bot.add_view(StartCardView())

    async def cog_unload(self) -> None:
        await self.enka.close()

    def in_bot_channel(self, channel: discord.abc.Messageable | None) -> bool:
        if channel is None or isinstance(channel, discord.Thread):
            return False
        channel_id = getattr(channel, "id", None)
        return isinstance(channel_id, int) and is_bot_channel(channel_id)

    async def _require_channel(self, interaction: discord.Interaction) -> bool:
        if not self.in_bot_channel(interaction.channel):
            await interaction.response.send_message(t(msg.ERR_02), ephemeral=True)
            return False
        return True

    @app_commands.command(name="setup", description=msg.MSG_03)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def setup_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if self.bot.user is None:
            await interaction.followup.send(t(msg.ERR_12), ephemeral=True)
            return
        if CHANNEL_ID == 0:
            await interaction.followup.send(t(msg.ERR_05), ephemeral=True)
            return
        channel = interaction.client.get_channel(CHANNEL_ID)
        if channel is None:
            try:
                channel = await interaction.client.fetch_channel(CHANNEL_ID)
            except discord.HTTPException as e:
                logger.warning("対象チャンネルを取得できませんでした channel=%s err=%s", CHANNEL_ID, e)
                await interaction.followup.send(t(msg.ERR_19), ephemeral=True)
                return
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(t(msg.ERR_19), ephemeral=True)
            return

        me = channel.guild.me if channel.guild is not None else None
        if me is None:
            await interaction.followup.send(t(msg.ERR_06), ephemeral=True)
            return
        perms = channel.permissions_for(me)
        missing: list[str] = []
        if not perms.view_channel:
            missing.append(t(msg.MSG_10))
        if not perms.send_messages:
            missing.append(t(msg.MSG_11))
        if not perms.embed_links:
            missing.append(t(msg.MSG_12))
        if not perms.read_message_history:
            missing.append(t(msg.MSG_13))
        if missing:
            await interaction.followup.send(t(msg.ERR_08, perms="、".join(missing)), ephemeral=True)
            return

        try:
            pins = await channel.pins()
        except discord.HTTPException as e:
            logger.warning("ピン一覧の取得に失敗しました channel=%s err=%s", CHANNEL_ID, e)
            pins = []
        for pinned in pins:
            if is_guide_message(pinned, self.bot.user.id):
                try:
                    await pinned.unpin()
                except discord.HTTPException:
                    pass
                try:
                    await pinned.delete()
                except discord.HTTPException:
                    pass

        try:
            sent = await channel.send(embed=guide_embed(), view=StartCardView())
        except discord.HTTPException as e:
            logger.warning("案内の投稿に失敗しました channel=%s err=%s", CHANNEL_ID, e)
            await interaction.followup.send(t(msg.ERR_06), ephemeral=True)
            return

        if not perms.manage_messages:
            await interaction.followup.send(t(msg.ERR_07), ephemeral=True)
            return
        try:
            await sent.pin()
        except discord.HTTPException as e:
            logger.warning("案内のピン留めに失敗しました channel=%s err=%s", CHANNEL_ID, e)
            await interaction.followup.send(t(msg.ERR_07), ephemeral=True)
            return
        await interaction.followup.send(t(msg.MSG_14), ephemeral=True)

    @app_commands.command(name="reload", description=msg.MSG_08)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def reload_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await self.enka.refresh_store()
            refresh_catalog()
        except Exception:
            logger.exception("Enka のキャラ辞書の取り直しに失敗しました")
            await interaction.followup.send(t(msg.ERR_09), ephemeral=True)
            return
        await interaction.followup.send(t(msg.MSG_09), ephemeral=True)

    @app_commands.command(name="check", description=msg.MSG_45)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def check_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await self.enka.ensure_store()
            refresh_catalog()
            rows = collect_rows(self.enka)
        except Exception:
            logger.exception("全キャラ確認に失敗しました")
            await interaction.followup.send(t(msg.ERR_09), ephemeral=True)
            return
        text = format_report(rows)
        if len(text) > 1900:
            await interaction.followup.send(
                content=t(msg.MSG_46, count=len(rows), bad=len(problem_rows(rows)), notes=len(note_rows(rows))),
                file=discord.File(BytesIO(text.encode("utf-8")), filename="check.txt"),
                ephemeral=True,
            )
            return
        await interaction.followup.send(text, ephemeral=True)

    @app_commands.command(name="addchar", description=msg.MSG_58)
    @app_commands.rename(enka="number")
    @app_commands.describe(
        name=msg.MSG_60,
        enka=msg.MSG_61,
        element=msg.MSG_62,
        scale=msg.MSG_63,
        aliases=msg.MSG_64,
    )
    @app_commands.choices(
        element=[
            app_commands.Choice(name=label, value=key) for key, label in msg.MSG_ELEM.items()
        ],
        scale=[
            app_commands.Choice(name=label, value=key) for key, label in msg.MSG_SCALE.items()
        ],
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def addchar_cmd(
        self,
        interaction: discord.Interaction,
        name: str,
        enka: str,
        element: str,
        scale: str,
        aliases: str = "",
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        digits = "".join(c for c in enka if c.isdigit())
        if not 8 <= len(digits) <= 10:
            await interaction.followup.send(t(msg.ERR_16), ephemeral=True)
            return
        name_ja = name.strip()
        if not name_ja:
            await interaction.followup.send(t(msg.ERR_18), ephemeral=True)
            return
        alias_list = parse_aliases(aliases)
        if name_ja not in alias_list:
            alias_list.insert(0, name_ja)
        try:
            character = upsert_character(
                name_ja=name_ja,
                enka_id=digits,
                element=element,
                scale=scale,
                aliases=alias_list,
            )
        except Exception:
            logger.exception("キャラの登録に失敗しました")
            await interaction.followup.send(t(msg.ERR_18), ephemeral=True)
            return
        await interaction.followup.send(
            t(msg.MSG_66, name=character.name_ja, scale=msg.MSG_SCALE.get(scale, scale)),
            ephemeral=True,
        )

    @app_commands.command(name="addset", description=msg.MSG_59)
    @app_commands.describe(name=msg.MSG_60, set_id=msg.MSG_65, aliases=msg.MSG_64)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def addset_cmd(
        self,
        interaction: discord.Interaction,
        name: str,
        set_id: str,
        aliases: str = "",
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        name_ja = name.strip()
        normalized = set_id.strip().lower()
        if not name_ja:
            await interaction.followup.send(t(msg.ERR_18), ephemeral=True)
            return
        if not valid_set_id(normalized):
            await interaction.followup.send(t(msg.ERR_17), ephemeral=True)
            return
        try:
            row = upsert_set(set_id=normalized, name_ja=name_ja, aliases=parse_aliases(aliases))
        except Exception:
            logger.exception("セットの登録に失敗しました")
            await interaction.followup.send(t(msg.ERR_18), ephemeral=True)
            return
        await interaction.followup.send(t(msg.MSG_67, name=row["name_ja"]), ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            if interaction.response.is_done():
                await interaction.followup.send(t(msg.ERR_04), ephemeral=True)
            else:
                await interaction.response.send_message(t(msg.ERR_04), ephemeral=True)
            return
        raise error

    @app_commands.command(name="formula", description=msg.MSG_04)
    async def formula_cmd(self, interaction: discord.Interaction) -> None:
        if not await self._require_channel(interaction):
            return
        await interaction.response.send_message(embed=formula_embed(), ephemeral=True)

    @app_commands.command(name="uid", description=msg.MSG_05)
    @app_commands.describe(uid=msg.MSG_06)
    async def uid_cmd(self, interaction: discord.Interaction, uid: str) -> None:
        await self.begin_uid(interaction, uid)

    async def begin_uid(self, interaction: discord.Interaction, uid: str) -> None:
        """スラッシュと Modal の共通開始。選択は ephemeral、カードだけチャンネルへ。"""
        if not await self._require_channel(interaction):
            return
        digits = "".join(c for c in uid if c.isdigit())
        if not 8 <= len(digits) <= 10:
            await interaction.response.send_message(t(msg.ERR_15), ephemeral=True)
            return
        await interaction.response.send_message(t(msg.MSG_30), ephemeral=True)
        try:
            showcase = await self.enka.fetch_showcase(digits)
        except EnkaError as e:
            await interaction.edit_original_response(content=t(msg.ERR_ENKA.get(e.code, msg.ERR_12)))
            return
        if not showcase.avatars:
            await interaction.edit_original_response(content=t(msg.ERR_10))
            return
        session = UidSession(
            user_id=interaction.user.id,
            uid=showcase.uid,
            nickname=showcase.nickname,
            avatars=list(showcase.avatars),
        )
        message = await interaction.original_response()
        self.sessions.put(message.id, session)
        view = UidPickView(self, message.id)
        await interaction.edit_original_response(
            content=t(msg.MSG_31, nickname=showcase.nickname, uid=showcase.uid),
            view=view,
        )

    def _public_channel(self, interaction: discord.Interaction) -> discord.TextChannel | None:
        channel = interaction.channel
        if isinstance(channel, discord.TextChannel) and self.in_bot_channel(channel):
            return channel
        got = self.bot.get_channel(CHANNEL_ID)
        if isinstance(got, discord.TextChannel):
            return got
        return None

    def _swap_pick_view(self, session_key: int, old: UidPickView | None = None) -> UidPickView:
        if old is not None:
            old.stop()
        return UidPickView(self, session_key)

    async def _render_png(self, session: UidSession) -> bytes | None:
        avatar = session.selected_avatar()
        if avatar is None:
            return None
        build = None
        if session.build_id:
            build = next((b for b in avatar.character.builds if b.id == session.build_id), None)
        if build is None and avatar.character.builds:
            build = avatar.character.builds[0]
        if build is None:
            return None
        await self.enka.ensure_store()
        portrait_keys = self.enka.portrait_names(avatar.avatar_id, avatar.skill_depot_id, avatar.costume_id)
        icon_names: list[str] = [*portrait_keys, avatar.icon, avatar.splash_icon]
        if avatar.weapon:
            icon_names.append(avatar.weapon.icon)
        icon_names.extend(icon for icon, _level in avatar.skills)
        icon_names.extend(avatar.constellation_icons)
        icon_names.extend(piece.icon or "" for piece in avatar.pieces)
        icons = await self.enka.download_icons(icon_names)
        portraits: list[bytes] = []
        for key in [*portrait_keys, avatar.splash_icon, avatar.icon]:
            data = icons.get(key) if key else None
            if data:
                portraits.append(data)
        if not portraits:
            logger.warning(
                "立ち絵を取得できませんでした avatar_id=%s keys=%s",
                avatar.avatar_id,
                portrait_keys,
            )
        weapon_bytes = icons.get(avatar.weapon.icon) if avatar.weapon else None
        showcase = EnkaShowcase(
            uid=session.uid,
            nickname=session.nickname,
            level=0,
            avatars=session.avatars,
            ttl=0,
        )
        try:
            return await asyncio.to_thread(
                render_build_card,
                showcase,
                avatar,
                build,
                portrait_bytes=portraits,
                weapon_bytes=weapon_bytes,
                icon_bytes=icons,
            )
        except Exception:
            logger.exception("ビルドカードの生成に失敗しました")
            return None

    async def _finish_public_card(
        self,
        interaction: discord.Interaction,
        session: UidSession,
        *,
        session_key: int,
        view: UidPickView | None = None,
    ) -> None:
        """カード画像だけチャンネルに出し、選択はそのまま残す。"""
        avatar = session.selected_avatar()
        png = await self._render_png(session)
        if avatar is None or png is None:
            await interaction.edit_original_response(content=t(msg.ERR_13), view=None)
            return
        channel = self._public_channel(interaction)
        if channel is None:
            await interaction.edit_original_response(content=t(msg.ERR_13), view=None)
            return
        file = discord.File(fp=BytesIO(png), filename="build.png")
        try:
            await channel.send(
                file=file,
                view=CardMessageView(
                    t(msg.MSG_33, nickname=session.nickname, character=avatar.name_ja)
                ),
            )
        except discord.HTTPException:
            logger.warning("カードの投稿に失敗しました channel=%s", channel.id)
            await interaction.edit_original_response(content=t(msg.ERR_13), view=None)
            return
        session.reset_pick()
        await interaction.edit_original_response(
            content=t(msg.MSG_34, character=avatar.name_ja),
            view=self._swap_pick_view(session_key, view),
        )

    async def publish_card(self, interaction: discord.Interaction, view: UidPickView) -> None:
        """選択完了後、チャンネルへカードだけ出す。"""
        session = self.sessions.get(view.session_key)
        avatar = session.selected_avatar() if session else None
        if session is None or avatar is None:
            await interaction.response.send_message(t(msg.ERR_03), ephemeral=True)
            return
        await interaction.response.defer()
        await self._finish_public_card(interaction, session, session_key=view.session_key, view=view)

    async def refresh_uid_session(self, interaction: discord.Interaction, view: UidPickView) -> None:
        """同じ UID の紹介枠を Enka から取り直す。"""
        session = self.sessions.get(view.session_key)
        if session is None:
            await interaction.response.send_message(t(msg.ERR_03), ephemeral=True)
            return
        for item in view.children:
            item.disabled = True
        await interaction.response.edit_message(content=t(msg.MSG_30), view=view)
        try:
            showcase = await self.enka.fetch_showcase(session.uid, force=True)
        except EnkaError as e:
            await interaction.edit_original_response(
                content=t(msg.ERR_ENKA.get(e.code, msg.ERR_12)),
                view=self._swap_pick_view(view.session_key, view),
            )
            return
        if not showcase.avatars:
            await interaction.edit_original_response(
                content=t(msg.ERR_10),
                view=self._swap_pick_view(view.session_key, view),
            )
            return
        session.apply_showcase(showcase.uid, showcase.nickname, showcase.avatars)
        await interaction.edit_original_response(
            content=t(msg.MSG_56),
            view=self._swap_pick_view(view.session_key, view),
        )

    @app_commands.command(name="ping", description=msg.MSG_07)
    async def ping_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            t(msg.MSG_15, ms=str(round(self.bot.latency * 1000))),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BuildCog(bot))
