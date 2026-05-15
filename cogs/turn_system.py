import datetime

import discord
from discord.ext import commands

from utils.turn_service import advance_player_turn


TURN_COOLDOWN_SECONDS = 300


class TurnSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_use = {}

    def _cooldown_remaining(self, user_id):
        last = self.last_use.get(user_id)
        if not last:
            return 0
        elapsed = (datetime.datetime.now(datetime.timezone.utc) - last).total_seconds()
        return max(0, int(TURN_COOLDOWN_SECONDS - elapsed))

    async def _send_cooldown_notice(self, ctx, remaining):
        minutes, seconds = divmod(remaining, 60)
        tempo = f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"
        await ctx.send(
            f"⏳ {ctx.author.mention}, `.passar_turno` está em recarga. "
            f"Use novamente em `{tempo}`. O turno não foi avançado.",
            delete_after=20,
        )

    def _build_embed(self, ctx, updates):
        embed = discord.Embed(title="⏳ Turno Avançado", color=0x2b2d31)
        embed.description = f"{ctx.author.mention} avançou o turno. Recargas e durações foram atualizadas."

        if not updates:
            embed.add_field(name="Sem recargas ativas", value="Nenhum cooldown ou efeito temporário precisava ser reduzido.", inline=False)
            return embed

        for item in updates[:12]:
            embed.add_field(
                name=f"{item['type']} • {item['status']}",
                value=item["text"],
                inline=False,
            )

        if len(updates) > 12:
            embed.set_footer(text=f"Mostrando 12 de {len(updates)} atualizações.")
        return embed

    @commands.command(name="passar_turno")
    async def passar_turno(self, ctx):
        if not ctx.guild:
            return await ctx.send("❌ `.passar_turno` precisa ser usado dentro de um servidor.")

        remaining = self._cooldown_remaining(ctx.author.id)
        if remaining > 0:
            return await self._send_cooldown_notice(ctx, remaining)

        self.last_use[ctx.author.id] = datetime.datetime.now(datetime.timezone.utc)

        updates = advance_player_turn(ctx.author.id)
        await ctx.send(embed=self._build_embed(ctx, updates))


async def setup(bot):
    await bot.add_cog(TurnSystem(bot))
