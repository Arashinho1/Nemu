import discord
from discord.ext import commands, tasks
import database
from utils import logic

class PretensaoSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.verificador_pretensao.start()

    def cog_unload(self):
        self.verificador_pretensao.cancel()

    @tasks.loop(minutes=1)
    async def verificador_pretensao(self):
        config = database.get_config_pretensao()
        if not config or not config[0]: return
        canal = self.bot.get_channel(config[0])
        if not canal: return
        
        deve_abrir = logic.esta_na_janela_pretensao(config)
        perms = canal.overwrites_for(canal.guild.default_role)
        if perms.send_messages != deve_abrir:
            perms.send_messages = deve_abrir
            await canal.set_permissions(canal.guild.default_role, overwrite=perms)
            await canal.send(f"📢 Sistema de Pretensão agora: {'ABERTO 🔓' if deve_abrir else 'FECHADO 🔒'}")

    @commands.command(name="pretensão")
    async def pretensao_status(self, ctx):
        config = database.get_config_pretensao()
        if not config or not config[0]: return await ctx.send("❌ Sistema não configurado.")
        esta_aberto = logic.esta_na_janela_pretensao(config)
        await ctx.send(f"🚦 Status da Pretensão: {'🟢 ABERTO' if esta_aberto else '🔴 FECHADO'}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        config = database.get_config_pretensao()
        if config and message.channel.id == config[0]:
            if not logic.esta_na_janela_pretensao(config):
                if not message.author.guild_permissions.administrator: await message.delete()
                return
            
            if not message.content.startswith(self.bot.command_prefix):
                v_id = message.content.strip()
                with database.get_connection() as conn:
                    vaga_res = conn.execute('SELECT nome, categoria FROM vagas WHERE vaga_id = ?', (v_id,)).fetchone()
                if vaga_res:
                    sucesso, msg = await logic.atribuir_vaga_logica(message.guild, message.author, vaga_res[0])
                    await message.channel.send(f"{'✅' if sucesso else '❌'} {message.author.mention}: {msg}")

async def setup(bot):
    await bot.add_cog(PretensaoSystem(bot))
