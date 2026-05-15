import discord
from discord.ext import commands
from discord.ext.commands import has_permissions, CommandNotFound, MissingPermissions, CheckFailure
import database
import logging
import os
import random
import sqlite3
import subprocess
import sys
import atexit
from datetime import datetime
from utils.permissions import guild_owner_only

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("nemu")

_lock_file = None

def acquire_single_instance_lock():
    global _lock_file
    lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nemu.lock")
    _lock_file = open(lock_path, "a+b")
    if os.path.getsize(lock_path) == 0:
        _lock_file.write(b" ")
        _lock_file.flush()

    if msvcrt:
        try:
            _lock_file.seek(0)
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            _lock_file.close()
            _lock_file = None
            print("Outra instancia do Nemu ja esta rodando. Encerrando esta copia.")
            sys.exit(0)

    _lock_file.seek(0)
    _lock_file.truncate()
    _lock_file.write(str(os.getpid()).encode("ascii"))
    _lock_file.flush()


def release_single_instance_lock():
    global _lock_file
    if not _lock_file:
        return
    try:
        _lock_file.seek(0)
        if msvcrt:
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        _lock_file.close()
    except OSError:
        pass
    _lock_file = None


acquire_single_instance_lock()
atexit.register(release_single_instance_lock)

# ---------------- CONFIG ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None, case_insensitive=True)

async def setup_hook():
    database.setup_db()
    # Lista de extensões para carregar automaticamente
    extensions = ["pretensao_system", "vagas_system", "player_system", "pericia_system", "guide_system", "potencial_system", "kido_system", "tecnica_system", "turn_system"]
    for ext in extensions:
        try:
            await bot.load_extension(f"cogs.{ext}")
            logger.info("Modulo %s carregado com sucesso.", ext)
        except Exception as e:
            logger.exception("Falha ao carregar modulo %s.", ext)
    try:
        from utils.profile_template import DESKTOP_SIZE, background_image, load_font, load_symbol_font
        from utils.kido_template import KIDO_SIZE, _kido_background_image
        from utils.tecnica_template import TECNICA_SIZE, _background_image

        background_image(DESKTOP_SIZE)
        _kido_background_image(KIDO_SIZE)
        _background_image(TECNICA_SIZE)
        load_font(32, bold=True, display=True)
        load_symbol_font(32)
        logger.info("Caches de renderizacao aquecidos.")
    except Exception:
        logger.exception("Falha ao aquecer caches de renderizacao.")

bot.setup_hook = setup_hook

@bot.event
async def on_ready():
    logger.info("%s online e operante.", bot.user.name)
    # Define o status visual do bot
    activity = discord.Game(name="Bleach RPG | .guia")
    await bot.change_presence(status=discord.Status.online, activity=activity)

async def get_log_channel():
    canal_id = database.get_canal_logs()
    if not canal_id:
        return None
    canal = bot.get_channel(canal_id)
    if canal:
        return canal
    try:
        return await bot.fetch_channel(canal_id)
    except discord.DiscordException:
        logger.warning("Canal de logs configurado nao foi encontrado: %s", canal_id)
        return None

@bot.event
async def on_command(ctx):
    canal = await get_log_channel()
    if not canal:
        return

    comando = ctx.message.content[len(ctx.prefix):].strip() if ctx.prefix else ctx.message.content.strip()
    embed = discord.Embed(title="📋 Log: Comando Executado", color=0x6d2e8f)
    embed.add_field(name="Usuário", value=f"{ctx.author.display_name} ({ctx.author.id})", inline=False)
    embed.add_field(name="Servidor", value=ctx.guild.name if ctx.guild else "Mensagem direta", inline=False)
    embed.add_field(name="Comando", value=comando[:900] or "N/A", inline=False)
    embed.add_field(name="Canal", value=ctx.channel.mention if hasattr(ctx.channel, "mention") else str(ctx.channel), inline=False)
    embed.set_footer(text=f"Hoje às {datetime.now().strftime('%H:%M')}")
    try:
        await canal.send(embed=embed)
    except Exception:
        logger.exception("Falha ao enviar log de comando.")

# ---------------- CHECK DE CANAL ----------------
@bot.check
async def global_channel_check(ctx):
    if ctx.author.guild_permissions.administrator: return True
    return not database.canal_bot_bloqueado(ctx.channel.id)

async def configurar_canal_logs(ctx, canal):
    canal = canal or ctx.channel
    database.setar_canal_logs(canal.id)
    await ctx.send(f"✅ Canal de logs definido para {canal.mention}.")

@bot.command(help="Define o canal de logs de comandos.")
@has_permissions(administrator=True)
async def setar_logs(ctx, canal: discord.TextChannel = None):
    await configurar_canal_logs(ctx, canal)

@bot.command(name="setar_log", help="Alias de .setar_logs.")
@has_permissions(administrator=True)
async def setar_log(ctx, canal: discord.TextChannel = None):
    await configurar_canal_logs(ctx, canal)

async def configurar_canal_historico(ctx, canal):
    canal = canal or ctx.channel
    database.setar_canal_historico(canal.id)
    await ctx.send(f"✅ Canal de histórico definido para {canal.mention}.")

@bot.command(help="Define o canal de histórico de movimentação de pontos.")
@has_permissions(administrator=True)
async def setar_historico(ctx, canal: discord.TextChannel = None):
    await configurar_canal_historico(ctx, canal)

async def bloquear_bot_no_canal(ctx, canal):
    canal = canal or ctx.channel
    database.bloquear_canal_bot(canal.id)
    await ctx.send(f"🔒 O bot não aceitará comandos de jogadores em {canal.mention}. Administradores continuam liberados.")

@bot.command(help="(Admin) Bloqueia comandos do bot em um canal.")
@has_permissions(administrator=True)
async def restringir_bot(ctx, canal: discord.TextChannel = None):
    await bloquear_bot_no_canal(ctx, canal)

@bot.command(help="(Admin) Alias antigo de .restringir_bot.")
@has_permissions(administrator=True)
async def setar_bot(ctx, canal: discord.TextChannel = None):
    await bloquear_bot_no_canal(ctx, canal)

@bot.command(help="(Admin) Libera comandos do bot em um canal bloqueado.")
@has_permissions(administrator=True)
async def liberar_bot(ctx, canal: discord.TextChannel = None):
    canal = canal or ctx.channel
    database.liberar_canal_bot(canal.id)
    await ctx.send(f"🔓 O bot voltou a aceitar comandos de jogadores em {canal.mention}.")

@bot.command(help="(Admin) Lista canais onde o bot está bloqueado.")
@has_permissions(administrator=True)
async def bloqueios_bot(ctx):
    canais = database.listar_canais_bloqueados_bot()
    if not canais:
        return await ctx.send("✅ Nenhum canal bloqueado. O bot aceita comandos em todos os canais.")

    mencoes = []
    for canal_id in canais:
        canal = bot.get_channel(canal_id)
        mencoes.append(canal.mention if canal else f"`{canal_id}`")
    await ctx.send("🔒 **Canais bloqueados:**\n" + "\n".join(mencoes))

# ---------------- TRATAMENTO DE ERROS ----------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandNotFound):
        return
    if isinstance(error, MissingPermissions):
        return await ctx.send("❌ Você não tem permissão para usar este comando.", delete_after=7)
    if isinstance(error, CheckFailure):
        if database.canal_bot_bloqueado(ctx.channel.id):
            return await ctx.send("❌ Comandos do bot estão bloqueados neste canal.", delete_after=5)
        return await ctx.send("❌ Você não tem permissão para usar este comando.", delete_after=7)
    
    logger.exception("Erro no comando '%s'.", ctx.command, exc_info=error)
    await ctx.send(f"⚠️ Ocorreu um erro inesperado: {error}", delete_after=10)

# ---------------- UTILITÁRIOS ----------------
@bot.command(help="(Admin) Recarrega um módulo do bot sem reiniciar.")
@guild_owner_only()
async def reload(ctx, modulo: str = None):
    if not modulo:
        return await ctx.send("❌ Informe um módulo ou use `.reload geral`.")
    if modulo.lower() in ("geral", "bot", "restart", "reiniciar"):
        await ctx.send("🔄 Reiniciando o bot para aplicar todas as alterações...")
        logger.info("Reinicio geral solicitado por %s (%s).", ctx.author, ctx.author.id)
        script_path = os.path.abspath(__file__)
        cwd = os.path.dirname(script_path)
        release_single_instance_lock()
        subprocess.Popen([sys.executable, script_path], cwd=cwd)
        await bot.close()
        os._exit(0)
        return

    try:
        await bot.reload_extension(modulo)
        await ctx.send(f"🔄 Módulo `{modulo}` recarregado com sucesso!")
    except Exception as e:
        await ctx.send(f"❌ Falha ao recarregar `{modulo}`: {e}")

# ---------------- 2FA LOGIC ----------------
class TwoFactorModal(discord.ui.Modal):
    def __init__(self, action_callback, code):
        super().__init__(title="Autenticação de Dois Fatores")
        self.action_callback = action_callback
        self.code = code
        self.input = discord.ui.TextInput(label=f"Digite o código: {code}", placeholder="Insira o código acima para confirmar")
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.input.value == self.code:
            await self.action_callback(interaction)
        else:
            await interaction.response.send_message("❌ Código incorreto. Operação cancelada.", ephemeral=True)

@bot.command(help="(Dono) Apaga TODOS os dados do bot (Vagas, Skills, Configurações e Fichas).")
@guild_owner_only()
async def apagar_servidor(ctx):
    class ConfirmView(discord.ui.View):
        def __init__(self, user_id):
            super().__init__(timeout=30)
            self.user_id = user_id

        async def check_owner(self, interaction):
            if interaction.user.id == self.user_id:
                return True
            await interaction.response.send_message("❌ Apenas quem iniciou esta confirmação pode responder.", ephemeral=True)
            return False
        
        async def actual_delete(self, interaction):
            with database.get_connection() as conn:
                tables = ['config_logs', 'config_historico', 'config_comandos', 'config_pretensao', 'personagens', 'potenciais', 
                          'player_potencial', 'vagas', 'player_vagas', 'vagas_vinculo', 'pericias_base', 
                          'player_pericias', 'kido_estado', 'kido_usos', 'kido_tecnicas',
                          'tecnica_estado', 'tecnica_usos', 'tecnicas', 'attribute_modifiers']
                for t in tables:
                    try:
                        conn.execute(f"DELETE FROM {t}")
                    except sqlite3.OperationalError:
                        logger.warning("Tabela inexistente ao apagar servidor: %s", t)
                conn.commit()
            await interaction.response.edit_message(content="💥 **O servidor foi completamente resetado.** Tudo foi apagado.", view=None)

        @discord.ui.button(label="APAGAR TUDO", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not await self.check_owner(interaction):
                return
            code = str(random.randint(1000, 9999))
            await interaction.response.send_modal(TwoFactorModal(self.actual_delete, code))

        @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not await self.check_owner(interaction):
                return
            await interaction.response.edit_message(content="Ação cancelada.", view=None)

    await ctx.send("🚨 **PERIGO:** Isso apagará vagas, skills, configurações e fichas. Confirmar?", view=ConfirmView(ctx.author.id))

@bot.command(help="(Dono) Apaga apenas o progresso dos jogadores (Fichas, Vagas preenchidas, etc).")
@guild_owner_only()
async def resetar_servidor(ctx):
    class ConfirmView(discord.ui.View):
        def __init__(self, user_id):
            super().__init__(timeout=30)
            self.user_id = user_id

        async def check_owner(self, interaction):
            if interaction.user.id == self.user_id:
                return True
            await interaction.response.send_message("❌ Apenas quem iniciou esta confirmação pode responder.", ephemeral=True)
            return False

        async def actual_reset(self, interaction):
            with database.get_connection() as conn:
                tables = ['personagens', 'player_potencial', 'player_vagas', 'player_pericias',
                          'kido_estado', 'kido_usos', 'tecnica_estado', 'tecnica_usos',
                          'attribute_modifiers']
                for t in tables:
                    try:
                        conn.execute(f"DELETE FROM {t}")
                    except sqlite3.OperationalError:
                        logger.warning("Tabela inexistente ao resetar servidor: %s", t)
                try:
                    conn.execute("DELETE FROM tecnicas WHERE classificacao = 'criado'")
                    conn.execute("DELETE FROM kido_tecnicas WHERE classificacao = 'criado'")
                except sqlite3.OperationalError:
                    logger.warning("Tabela de técnicas inexistente ao limpar criações de jogadores.")
                conn.commit()
            await interaction.response.edit_message(content="🧹 **Reset de Jogadores concluído.** Vagas e Skills base foram mantidas.", view=None)

        @discord.ui.button(label="RESETAR JOGADORES", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not await self.check_owner(interaction):
                return
            code = str(random.randint(1000, 9999))
            await interaction.response.send_modal(TwoFactorModal(self.actual_reset, code))

        @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not await self.check_owner(interaction):
                return
            await interaction.response.edit_message(content="Ação cancelada.", view=None)

    await ctx.send("⚠️ **AVISO:** Isso apagará apenas as fichas e progressos. Vagas e Skills base serão mantidas. Confirmar?", view=ConfirmView(ctx.author.id))

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("Defina a variavel de ambiente DISCORD_TOKEN antes de iniciar o bot.")

bot.run(token)
