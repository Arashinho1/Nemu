import discord
from discord import ui
import sqlite3
from database import get_connection, get_vagas_bonus
from utils.logic import get_potencial_info, calcular_reiatsu, nivel_reiatsu

class PaginatorView(ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.current_page = 0
        if self.embeds: self.embeds[0].set_footer(text=f"Página 1 de {len(self.embeds)}")

    async def update_message(self, interaction: discord.Interaction):
        embed = self.embeds[self.current_page]
        embed.set_footer(text=f"Página {self.current_page + 1} de {len(self.embeds)}")
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="⏮️", style=discord.ButtonStyle.grey)
    async def first_page(self, interaction, button):
        self.current_page = 0
        await self.update_message(interaction)

    @ui.button(label="⬅️", style=discord.ButtonStyle.grey)
    async def prev_page(self, interaction, button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)

    @ui.button(label="➡️", style=discord.ButtonStyle.grey)
    async def next_page(self, interaction, button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await self.update_message(interaction)

    @ui.button(label="⏭️", style=discord.ButtonStyle.grey)
    async def last_page(self, interaction, button):
        self.current_page = len(self.embeds) - 1
        await self.update_message(interaction)
