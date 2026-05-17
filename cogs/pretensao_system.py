import discord
from discord.ext import commands, tasks
from discord import ui
import database
from utils import logic
import sqlite3

class VagaToggleView(ui.View):
    def __init__(self, categoria):
        super().__init__(timeout=180)
        self.categoria = categoria
        self.add_item(VagaSelect(categoria))

class VagaSelect(ui.Select):
    def __init__(self, categoria):
        with database.get_connection() as conn:
            vagas = conn.execute(
                "SELECT nome, vaga_id, bloqueada FROM vagas WHERE categoria = ?", 
                (categoria,)
            ).fetchall()
        
        options = [
            discord.SelectOption(
                label=v[0], 
                value=v[0], 
                description=f"ID: {v[1]} | Status: {'🔒 Bloqueada' if v[2] else '🔓 Liberada'}"
            ) for v in vagas[:25]
        ]
        super().__init__(placeholder="Escolha a vaga para configurar...", options=options)

    async def callback(self, interaction: discord.Interaction):
        vaga_nome = self.values[0]
        embed = discord.Embed(title=f"Configurar Vaga: {vaga_nome}", color=0x3498db)
        await interaction.response.edit_message(embed=embed, view=VagaActionView(vaga_nome))

class VagaActionView(ui.View):
    def __init__(self, vaga_nome):
        super().__init__(timeout=60)
        self.vaga_nome = vaga_nome

    async def _voltar_ao_inicio(self, interaction, status_msg):
        with database.get_connection() as conn:
            cats = [row[0] for row in conn.execute("SELECT DISTINCT categoria FROM vagas").fetchall()]
        
        if not cats:
            return await interaction.response.edit_message(content="❌ Nenhuma vaga cadastrada.", embed=None, view=None)
        
        view = ui.View()
        view.add_item(CategoriaSelect(cats))
        await interaction.response.edit_message(
            content=f"{status_msg}\n\nSelecione a categoria das vagas que deseja configurar:",
            embed=None,
            view=view
        )

    @ui.button(label="Liberar", style=discord.ButtonStyle.success)
    async def liberar(self, interaction, button):
        with database.get_connection() as conn:
            conn.execute("UPDATE vagas SET bloqueada = 0 WHERE nome = ?", (self.vaga_nome,))
            conn.commit()
        await self._voltar_ao_inicio(interaction, f"✅ Vaga `{self.vaga_nome}` liberada para resgate.")

    @ui.button(label="Bloquear", style=discord.ButtonStyle.danger)
    async def bloquear(self, interaction, button):
        with database.get_connection() as conn:
            conn.execute("UPDATE vagas SET bloqueada = 1 WHERE nome = ?", (self.vaga_nome,))
            conn.commit()
        await self._voltar_ao_inicio(interaction, f"🔒 Vaga `{self.vaga_nome}` bloqueada para absolutamente todos.")

class CategoriaSelect(ui.Select):
    def __init__(self, categorias):
        options = [discord.SelectOption(label=c, value=c) for c in categorias[:25]]
        super().__init__(placeholder="Escolha a categoria...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=f"Filtrando vagas da categoria: **{self.values[0]}**",
            view=VagaToggleView(self.values[0])
        )

class PretensaoSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.verificador_pretensao.start()

    def cog_unload(self):
        self.verificador_pretensao.cancel()

    @commands.command(name="criar_pretensão")
    @commands.has_permissions(administrator=True)
    async def criar_pretensao(self, ctx, canal: discord.TextChannel = None):
        """Define o canal onde a pretensão irá ocorrer."""
        target = canal or ctx.channel
        with database.get_connection() as conn:
            conn.execute("UPDATE config_pretensao SET canal_id = ? WHERE id = 1", (target.id,))
            conn.commit()
        await ctx.send(f"🎯 Canal de Pretensão definido para {target.mention}.")

    @commands.command(name="pretensão_config")
    @commands.has_permissions(administrator=True)
    async def pretensao_config(self, ctx):
        """Abre o menu para liberar ou bloquear vagas."""
        with database.get_connection() as conn:
            cats = [row[0] for row in conn.execute("SELECT DISTINCT categoria FROM vagas").fetchall()]
        
        if not cats: return await ctx.send("❌ Nenhuma vaga cadastrada.")
        
        view = ui.View()
        view.add_item(CategoriaSelect(cats))
        await ctx.send("Selecione a categoria das vagas que deseja configurar:", view=view)

    @tasks.loop(minutes=1)
    async def verificador_pretensao(self):
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            config = conn.execute("SELECT canal_id, hora_abrir, hora_fechar, dias_semana, anunciado FROM config_pretensao WHERE id = 1").fetchone()
        
        if not config or not config['canal_id']: return
        canal = self.bot.get_channel(config['canal_id'])
        if not canal: return
        
        deve_abrir = logic.esta_na_janela_pretensao((config['canal_id'], config['hora_abrir'], config['hora_fechar'], config['dias_semana']))
        perms = canal.overwrites_for(canal.guild.default_role)
        
        if perms.send_messages != deve_abrir:
            perms.send_messages = deve_abrir
            await canal.set_permissions(canal.guild.default_role, overwrite=perms)
            
            if deve_abrir:
                # Anuncio Inicial
                await canal.send(f"📢 @everyone **O SISTEMA DE PRETENSÃO COMEÇOU!** 🔓\nMandem o ID da vaga desejada abaixo.")
                # Envia o comando .vagas automaticamente
                vagas_cmd = self.bot.get_command("vagas")
                ctx = await self.bot.get_context(await canal.send("⌛ Carregando lista de vagas..."))
                await ctx.invoke(vagas_cmd)
                
                with database.get_connection() as conn:
                    conn.execute("UPDATE config_pretensao SET anunciado = 1 WHERE id = 1")
                    conn.commit()
            else:
                await canal.send("🔒 **Sistema de Pretensão Encerrado.** O chat foi silenciado.")
                with database.get_connection() as conn:
                    conn.execute("UPDATE config_pretensao SET anunciado = 0 WHERE id = 1")
                    conn.commit()

    @commands.command(name="pretensão")
    async def pretensao_status(self, ctx):
        config = database.get_config_pretensao()
        if not config or not config[0]: return await ctx.send("❌ Sistema não configurado.")
        esta_aberto = logic.esta_na_janela_pretensao(config)
        await ctx.send(f"🚦 Status da Pretensão: {'🟢 ABERTO' if esta_aberto else '🔴 FECHADO'}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            config = conn.execute("SELECT canal_id, hora_abrir, hora_fechar, dias_semana FROM config_pretensao WHERE id = 1").fetchone()

        if config and message.channel.id == config['canal_id']:
            if not logic.esta_na_janela_pretensao((config['canal_id'], config['hora_abrir'], config['hora_fechar'], config['dias_semana'])):
                if not message.author.guild_permissions.administrator: await message.delete()
                return
            
            if not message.content.startswith(self.bot.command_prefix):
                v_id = message.content.strip()
                with database.get_connection() as conn:
                    vaga_res = conn.execute('SELECT nome, bloqueada FROM vagas WHERE vaga_id = ?', (v_id,)).fetchone()
                
                if vaga_res:
                    if vaga_res[1]: # Se bloqueada
                        return await message.channel.send(f"❌ {message.author.mention}: A vaga `{vaga_res[0]}` está bloqueada pela Staff.", delete_after=10)
                    
                    sucesso, msg = await logic.atribuir_vaga_logica(message.guild, message.author, vaga_res[0])
                    await message.channel.send(f"{'✅' if sucesso else '❌'} {message.author.mention}: {msg}")

async def setup(bot):
    await bot.add_cog(PretensaoSystem(bot))
