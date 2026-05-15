from datetime import datetime

import discord

import database


def _member_label(member_or_user_id):
    if hasattr(member_or_user_id, "display_name"):
        return f"{member_or_user_id.display_name} ({member_or_user_id.id})"
    if member_or_user_id:
        return f"<@{int(member_or_user_id)}> ({int(member_or_user_id)})"
    return "Sistema"


def _channel_label(channel):
    if not channel:
        return "N/A"
    return channel.mention if hasattr(channel, "mention") else str(channel)


async def get_history_channel(bot):
    canal_id = database.get_canal_historico()
    if not canal_id:
        return None
    canal = bot.get_channel(canal_id)
    if canal:
        return canal
    try:
        return await bot.fetch_channel(canal_id)
    except discord.DiscordException:
        return None


async def send_points_history(bot, *, action, point_type, quantity, receiver, giver=None, source_channel=None, details=None):
    canal = await get_history_channel(bot)
    if not canal:
        return

    details = details or {}
    color = 0x2ecc71 if action == "Recebimento" else 0x3498db
    embed = discord.Embed(title="📊 Histórico: Movimentação de Pontos", color=color)
    embed.add_field(name="Movimentação", value=action, inline=True)
    embed.add_field(name="Tipo", value=point_type, inline=True)
    embed.add_field(name="Quantidade", value=str(quantity), inline=True)
    embed.add_field(name="Quem deu", value=_member_label(giver), inline=False)
    embed.add_field(name="Quem recebeu", value=_member_label(receiver), inline=False)
    embed.add_field(name="Canal", value=_channel_label(source_channel), inline=False)

    if details.get("pool_label"):
        embed.add_field(
            name=details["pool_label"],
            value=f"`{details.get('pool_before', 0)}` → `{details.get('pool_after', 0)}`",
            inline=True,
        )

    if details.get("target_label"):
        embed.add_field(
            name=details["target_label"],
            value=f"`{details.get('target_before', 0)}` → `{details.get('target_after', 0)}`",
            inline=True,
        )

    if details.get("extra"):
        embed.add_field(name="Detalhes", value=details["extra"][:1000], inline=False)

    embed.set_footer(text=datetime.now().strftime("%d/%m/%Y às %H:%M"))
    try:
        await canal.send(embed=embed)
    except discord.DiscordException:
        return
