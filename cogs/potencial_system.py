import os
import re
import discord
import sqlite3
import shlex
from discord.ext import commands
from discord import ui
from database import get_connection
from utils.permissions import guild_owner_only, is_guild_owner
from utils.ui_components import PaginatorView
from utils.kido_service import ensure_kido_state


LOCAL_MEDIA_PREFIX = "local:"
POTENCIAL_MEDIA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "potenciais")
)
ALLOWED_MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def is_media_url(url):
    if not url:
        return True
    lowered = url.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _slugify_filename(value):
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_")
    return slug[:60] or "potencial"


def _local_media_ref(path):
    rel_path = os.path.relpath(os.path.abspath(path), os.path.dirname(os.path.dirname(__file__)))
    return LOCAL_MEDIA_PREFIX + rel_path.replace("\\", "/")


def _resolve_local_media(ref):
    if not ref or not ref.startswith(LOCAL_MEDIA_PREFIX):
        return None
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.abspath(os.path.join(root, ref[len(LOCAL_MEDIA_PREFIX):]))
    media_root = os.path.abspath(POTENCIAL_MEDIA_DIR)
    if path == media_root or not path.startswith(media_root + os.sep):
        return None
    return path


def apply_potential_image(embed, media_ref):
    if not media_ref:
        return None
    local_path = _resolve_local_media(media_ref)
    if local_path:
        if not os.path.exists(local_path):
            return None
        filename = os.path.basename(local_path)
        embed.set_image(url=f"attachment://{filename}")
        return discord.File(local_path, filename=filename)
    embed.set_image(url=media_ref)
    return None


def delete_local_media(ref):
    path = _resolve_local_media(ref)
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


async def send_potential_embed(ctx, embed, media_ref):
    file = apply_potential_image(embed, media_ref)
    if file:
        return await ctx.send(embed=embed, file=file)
    return await ctx.send(embed=embed)


def parse_consumo_reiryoku(value):
    text = (value or "").strip()
    if not text:
        return 0, 0
    parts = [part.strip() for part in text.replace(";", ",").replace("/", ",").split(",")]
    try:
        ativacao = int(parts[0]) if parts and parts[0] else 0
        turno = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    except ValueError:
        raise ValueError("Consumo de Reiryoku precisa usar numeros inteiros. Ex: 100, 25")
    if ativacao < 0 or turno < 0:
        raise ValueError("Consumo de Reiryoku nao pode ser negativo.")
    return ativacao, turno


class ModalConsumoPotencial(ui.Modal, title="Consumo de Potencial"):
    nome = ui.TextInput(label="Nome do Potencial", placeholder="Ex: Shikai")
    consumo = ui.TextInput(
        label="Reiryoku: ativacao, turno",
        placeholder="Ex: 100, 25 (vazio ou 0,0 se nao consumir)",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            custo_ativacao, custo_turno = parse_consumo_reiryoku(self.consumo.value)
            nome = self.nome.value.strip()
            with get_connection() as conn:
                res = conn.execute(
                    "SELECT nome FROM potenciais WHERE LOWER(nome) = LOWER(?)",
                    (nome,),
                ).fetchone()
                if not res:
                    return await interaction.response.send_message(f"❌ Potencial `{nome}` não encontrado.", ephemeral=True)
                conn.execute(
                    "UPDATE potenciais SET custo_ativacao = ?, custo_turno = ? WHERE nome = ?",
                    (custo_ativacao, custo_turno, res[0]),
                )
                conn.commit()
            await interaction.response.send_message(
                f"✅ Consumo de `{res[0]}` configurado: ativação `{custo_ativacao}`, por turno `{custo_turno}`.",
                ephemeral=True,
            )
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

class ModalPotencial(ui.Modal):
    def __init__(self, title, is_edit=False):
        super().__init__(title=title)
        self.is_edit = is_edit
        self.nome = ui.TextInput(label="Nome do Potencial", placeholder="Ex: Bankai")
        self.add_item(self.nome)
        self.mult = ui.TextInput(label="Multiplicador", placeholder="Ex: 1.5")
        self.add_item(self.mult)
        self.dur = ui.TextInput(label="Duração (Turnos)", placeholder="Ex: 5")
        self.add_item(self.dur)
        self.cd = ui.TextInput(label="Recarga (Turnos)", placeholder="Ex: 10")
        self.add_item(self.cd)
        self.consumo = ui.TextInput(
            label="Reiryoku: ativacao, turno",
            placeholder="Ex: 100, 25 (opcional: 0,0)",
            required=False,
        )
        self.add_item(self.consumo)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            nome = self.nome.value.strip()
            if not nome:
                return await interaction.response.send_message("❌ Informe o nome do potencial.", ephemeral=True)

            m, d, c = float(self.mult.value), int(self.dur.value), int(self.cd.value)
            custo_ativacao, custo_turno = parse_consumo_reiryoku(self.consumo.value)
            with get_connection() as conn:
                if self.is_edit:
                    res = conn.execute('SELECT 1 FROM potenciais WHERE nome = ?', (nome,)).fetchone()
                    if not res:
                        return await interaction.response.send_message(f"❌ Potencial `{nome}` não encontrado.", ephemeral=True)
                    conn.execute(
                        'UPDATE potenciais SET multiplicador=?, duracao=?, cooldown=?, custo_ativacao=?, custo_turno=? WHERE nome=?',
                        (m, d, c, custo_ativacao, custo_turno, nome),
                    )
                else:
                    res = conn.execute('SELECT 1 FROM potenciais WHERE nome = ?', (nome,)).fetchone()
                    if res:
                        return await interaction.response.send_message(
                            f"❌ Já existe um potencial chamado `{nome}`. Use **Editar Potencial** para alterar os valores.",
                            ephemeral=True
                        )
                    conn.execute(
                        'INSERT INTO potenciais (nome, multiplicador, duracao, cooldown, custo_ativacao, custo_turno) VALUES (?, ?, ?, ?, ?, ?)',
                        (nome, m, d, c, custo_ativacao, custo_turno),
                    )
                conn.commit()
            await interaction.response.send_message(f"✅ Potencial `{nome}` {'atualizado' if self.is_edit else 'criado'}!", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Multiplicador, duração, recarga e consumo precisam ser números válidos.", ephemeral=True)
        except sqlite3.IntegrityError:
            await interaction.response.send_message("❌ Já existe um potencial com esse nome.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

class ModalDeletarPotencial(ui.Modal, title='Deletar Potencial do Sistema'):
    nome = ui.TextInput(label="Nome do Potencial", placeholder="Digite o nome exato para apagar")

    async def on_submit(self, interaction: discord.Interaction):
        with get_connection() as conn:
            # Verifica se existe antes de tentar apagar
            res = conn.execute('SELECT 1 FROM potenciais WHERE nome = ?', (self.nome.value,)).fetchone()
            if not res:
                return await interaction.response.send_message(f"❌ Potencial `{self.nome.value}` não encontrado.", ephemeral=True)
            
            conn.execute('DELETE FROM potenciais WHERE nome = ?', (self.nome.value,))
            # Limpa dos jogadores também para evitar bugs
            conn.execute('DELETE FROM player_potencial WHERE potencial = ?', (self.nome.value,))
            conn.commit()
        await interaction.response.send_message(f"🗑️ Potencial `{self.nome.value}` removido permanentemente do sistema.", ephemeral=True)


class ModalImagemPotencial(ui.Modal):
    def __init__(self, user_id, potencial):
        super().__init__(title=f"Imagem de {potencial}"[:45])
        self.user_id = user_id
        self.potencial = potencial
        self.imagem_url = ui.TextInput(
            label="URL direta da imagem/GIF",
            placeholder="Ex: https://site/imagem.gif (Tenor/Giphy precisa ser link direto)",
            required=True,
            max_length=500,
        )
        self.add_item(self.imagem_url)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)

        imagem_url = self.imagem_url.value.strip()
        if not is_media_url(imagem_url):
            return await interaction.response.send_message("❌ A imagem/GIF precisa ser uma URL começando com `http://` ou `https://`.", ephemeral=True)

        with get_connection() as conn:
            res = conn.execute(
                "SELECT 1 FROM player_potencial WHERE user_id = ? AND potencial = ?",
                (self.user_id, self.potencial),
            ).fetchone()
            if not res:
                return await interaction.response.send_message(f"❌ Você não possui o potencial `{self.potencial}`.", ephemeral=True)
            conn.execute(
                "UPDATE player_potencial SET imagem_url = ? WHERE user_id = ? AND potencial = ?",
                (imagem_url, self.user_id, self.potencial),
            )
            conn.commit()

        await interaction.response.send_message(f"✅ Imagem/GIF de `{self.potencial}` configurado.", ephemeral=True)


class PotencialImagemSelect(ui.Select):
    def __init__(self, user_id, potenciais):
        self.potenciais = list(potenciais[:25])
        options = [
            discord.SelectOption(
                label=p["potencial"][:100],
                value=str(index),
                description=("Imagem configurada" if p["imagem_url"] else "Sem imagem configurada"),
            )
            for index, p in enumerate(self.potenciais)
        ]
        super().__init__(placeholder="Escolha o potencial para configurar a imagem...", options=options)
        self.user_id = user_id

    async def callback(self, interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        potencial = self.potenciais[int(self.values[0])]["potencial"]
        await interaction.response.send_modal(ModalImagemPotencial(self.user_id, potencial))


class PotencialImagemView(ui.View):
    def __init__(self, user_id, potenciais):
        super().__init__(timeout=120)
        self.add_item(PotencialImagemSelect(user_id, potenciais))

class PotencialView(ui.View):
    def __init__(self, user_id, is_admin=False, is_owner=False):
        super().__init__(timeout=60)
        self.user_id = user_id
        if is_admin:
            self.add_admin_buttons(is_owner)

    def add_admin_buttons(self, is_owner=False):
        btn_create = ui.Button(label="➕ Criar Potencial", style=discord.ButtonStyle.success)
        btn_create.callback = self.admin_create_callback
        self.add_item(btn_create)

        btn_edit = ui.Button(label="✏️ Editar Potencial", style=discord.ButtonStyle.secondary)
        btn_edit.callback = self.admin_edit_callback
        self.add_item(btn_edit)

        if not is_owner:
            return
        btn_delete = ui.Button(label="🗑️ Deletar Potencial", style=discord.ButtonStyle.danger)
        btn_delete.callback = self.admin_delete_callback
        self.add_item(btn_delete)

    async def admin_create_callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem usar este botão.", ephemeral=True)
        await interaction.response.send_modal(ModalPotencial("Criar Potencial"))

    async def admin_edit_callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem usar este botão.", ephemeral=True)
        await interaction.response.send_modal(ModalPotencial("Editar Potencial", True))

    async def admin_delete_callback(self, interaction: discord.Interaction):
        if not is_guild_owner(interaction.user, interaction.guild):
            return await interaction.response.send_message("❌ Apenas o criador do servidor pode deletar potenciais do sistema.", ephemeral=True)
        await interaction.response.send_modal(ModalDeletarPotencial())

    @ui.button(label="🖼️ Configurar Imagem", style=discord.ButtonStyle.secondary)
    async def config_image(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)

        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            potenciais = conn.execute(
                """
                SELECT potencial, imagem_url
                FROM player_potencial
                WHERE user_id = ?
                ORDER BY potencial COLLATE NOCASE
                """,
                (interaction.user.id,),
            ).fetchall()

        if not potenciais:
            return await interaction.response.send_message("❌ Você não possui potenciais para configurar.", ephemeral=True)

        await interaction.response.send_message(
            "Escolha qual potencial receberá sua imagem/GIF de liberação:",
            view=PotencialImagemView(interaction.user.id, potenciais),
            ephemeral=True,
        )

    @ui.button(label="📖 Ver Meus Potenciais", style=discord.ButtonStyle.primary)
    async def my_pots(self, interaction, button):
        with get_connection() as conn:
            res = conn.execute('''SELECT p.potencial, p.ativo, p.cooldown, pots.multiplicador, p.imagem_url,
                                         pots.custo_ativacao, pots.custo_turno
                                FROM player_potencial p JOIN potenciais pots ON p.potencial = pots.nome 
                                WHERE p.user_id = ?''', (interaction.user.id,)).fetchall()
        
        if not res:
            return await interaction.response.send_message("❌ Você não possui potenciais registrados.", ephemeral=True)
        
        embed = discord.Embed(title="🔥 Seus Potenciais", color=0xe67e22)
        for nome, ativo, cd, mult, imagem_url, custo_ativacao, custo_turno in res:
            status = "ATIVO 🔥" if ativo else (f"Recarga: {cd}t" if cd > 0 else "PRONTO ✅")
            midia = "\nImagem/GIF: ✅" if imagem_url else "\nImagem/GIF: ❌"
            consumo = f"\nReiryoku: ativação `{custo_ativacao or 0}` | turno `{custo_turno or 0}`"
            embed.add_field(name=nome, value=f"Multiplicador: `{mult}x`\nStatus: {status}{consumo}{midia}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class PotencialSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def ativar_potencial(self, ctx, nome):
        nome = nome.strip()
        if not nome:
            return await ctx.send("❌ Informe o potencial. Ex: `.p Shikai`.")

        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            potencial_existe = conn.execute(
                "SELECT nome FROM potenciais WHERE LOWER(nome) = LOWER(?)",
                (nome,),
            ).fetchone()
            if not potencial_existe:
                return await ctx.send(f"❌ Potencial `{nome}` não existe no sistema.")

            dados = conn.execute(
                """
                SELECT pp.potencial, pp.ativo, pp.cooldown, pp.dur_mod, pp.cd_mod, pp.mult_override,
                       pp.imagem_url, p.multiplicador, p.duracao, p.cooldown AS base_cooldown,
                       p.custo_ativacao, p.custo_turno
                FROM player_potencial pp
                JOIN potenciais p ON pp.potencial = p.nome
                WHERE pp.user_id = ? AND LOWER(pp.potencial) = LOWER(?)
                """,
                (ctx.author.id, nome),
            ).fetchone()

            if not dados:
                return await ctx.send(f"❌ Você não possui o potencial `{potencial_existe['nome']}`.")
            if dados["ativo"] == 1:
                cooldown = max(0, (dados["base_cooldown"] or 0) + (dados["cd_mod"] or 0))
                conn.execute(
                    """
                    UPDATE player_potencial
                    SET ativo = 0, turnos = 0, cooldown = ?
                    WHERE user_id = ? AND potencial = ?
                    """,
                    (cooldown, ctx.author.id, dados["potencial"]),
                )
                conn.commit()

                embed = discord.Embed(
                    title=f"🔥 {dados['potencial']} Desativado",
                    description=f"{ctx.author.mention} encerrou **{dados['potencial']}**.",
                    color=0xe67e22,
                )
                embed.add_field(name="Recarga", value=f"`{cooldown}` turno(s)", inline=True)
                return await send_potential_embed(ctx, embed, dados["imagem_url"])

            if dados["cooldown"] > 0:
                return await ctx.send(f"⏳ `{dados['potencial']}` está em recarga por mais `{dados['cooldown']}` turno(s).")

            turnos = max(1, (dados["duracao"] or 0) + (dados["dur_mod"] or 0))
            multiplicador = dados["mult_override"] if dados["mult_override"] and dados["mult_override"] > 0 else dados["multiplicador"]
            custo_ativacao = max(0, dados["custo_ativacao"] or 0)
            state = ensure_kido_state(ctx.author.id)
            if not state:
                return await ctx.send("❌ Personagem não encontrado.")
            if state["reiryoku_atual"] < custo_ativacao:
                return await ctx.send(
                    f"❌ Reiryoku insuficiente para ativar `{dados['potencial']}`: "
                    f"`{state['reiryoku_atual']}/{custo_ativacao}`."
                )
            if custo_ativacao > 0:
                conn.execute(
                    """
                    UPDATE kido_estado
                    SET reiryoku_atual = reiryoku_atual - ?
                    WHERE user_id = ?
                    """,
                    (custo_ativacao, ctx.author.id),
                )
            conn.execute(
                "UPDATE player_potencial SET ativo = 1, turnos = ?, cooldown = 0 WHERE user_id = ? AND potencial = ?",
                (turnos, ctx.author.id, dados["potencial"]),
            )
            conn.commit()

        embed = discord.Embed(
            title=f"🔥 {dados['potencial']} Liberado",
            description=f"{ctx.author.mention} liberou **{dados['potencial']}**.",
            color=0xe67e22,
        )
        embed.add_field(name="Multiplicador", value=f"`x{multiplicador}`", inline=True)
        embed.add_field(name="Duração", value=f"`{turnos}` turno(s)", inline=True)
        if custo_ativacao > 0 or dados["custo_turno"]:
            restante = max(0, state["reiryoku_atual"] - custo_ativacao)
            embed.add_field(
                name="Reiryoku",
                value=f"Ativação: `{custo_ativacao}` | Turno: `{dados['custo_turno'] or 0}`\nRestante: `{restante}/{state['reiryoku_max']}`",
                inline=False,
            )
        await send_potential_embed(ctx, embed, dados["imagem_url"])

    @commands.command(help="Menu de gerenciamento de potenciais e liberações.")
    async def potencial(self, ctx):
        is_adm = ctx.author.guild_permissions.administrator
        is_owner = is_guild_owner(ctx.author, ctx.guild)
        embed = discord.Embed(title="🔥 Gestão de Potenciais", color=0xe67e22)
        embed.description = "Utilize os botões para gerenciar suas liberações ou configurar o sistema (Staff)."
        await ctx.send(embed=embed, view=PotencialView(ctx.author.id, is_adm, is_owner))

    @commands.command(name="p", aliases=["liberar_potencial"], help="Ativa ou desativa um potencial. Uso: .p Shikai")
    async def liberar_potencial(self, ctx, *, nome: str = ""):
        await self.ativar_potencial(ctx, nome)

    @commands.command(
        name="imagem_potencial",
        aliases=["config_imagem_potencial", "potencial_imagem"],
        help='Configura sua imagem/GIF individual. Use: .imagem_potencial "Shikai" <url> ou envie um anexo com .imagem_potencial "Shikai"',
    )
    async def imagem_potencial(self, ctx, *, entrada: str = ""):
        entrada = entrada.strip()
        attachment = ctx.message.attachments[0] if ctx.message.attachments else None
        imagem_ref = None

        try:
            partes = shlex.split(entrada) if entrada else []
        except ValueError:
            return await ctx.send('❌ Não entendi o nome. Use aspas se tiver espaço: `.imagem_potencial "Nome do Potencial"`.')

        if partes and is_media_url(partes[-1]):
            imagem_ref = partes[-1]
            nome = " ".join(partes[:-1]).strip()
        else:
            nome = entrada

        if not nome:
            return await ctx.send('❌ Informe o potencial. Ex: `.imagem_potencial "Shikai"` com uma imagem anexada.')

        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            potencial = conn.execute(
                """
                SELECT potencial, imagem_url
                FROM player_potencial
                WHERE user_id = ? AND LOWER(potencial) = LOWER(?)
                """,
                (ctx.author.id, nome),
            ).fetchone()
            if not potencial:
                return await ctx.send(f"❌ Você não possui o potencial `{nome}`.")

        if attachment and not imagem_ref:
            ext = os.path.splitext(attachment.filename or "")[1].lower()
            if ext not in ALLOWED_MEDIA_EXTENSIONS:
                return await ctx.send("❌ Anexe uma imagem em `.png`, `.jpg`, `.jpeg`, `.gif` ou `.webp`.")
            if attachment.size and attachment.size > 25 * 1024 * 1024:
                return await ctx.send("❌ Essa imagem está muito grande. Use um arquivo de até 25 MB.")

            os.makedirs(POTENCIAL_MEDIA_DIR, exist_ok=True)
            filename = f"{ctx.author.id}_{_slugify_filename(potencial['potencial'])}{ext}"
            path = os.path.join(POTENCIAL_MEDIA_DIR, filename)
            await attachment.save(path)
            imagem_ref = _local_media_ref(path)

        if not imagem_ref:
            return await ctx.send(
                '❌ Envie uma imagem/GIF anexada ou coloque uma URL direta. Ex: `.imagem_potencial "Shikai" https://site/imagem.gif`.'
            )

        if potencial["imagem_url"] != imagem_ref:
            delete_local_media(potencial["imagem_url"])
        with get_connection() as conn:
            conn.execute(
                "UPDATE player_potencial SET imagem_url = ? WHERE user_id = ? AND potencial = ?",
                (imagem_ref, ctx.author.id, potencial["potencial"]),
            )
            conn.commit()

        origem = "arquivo anexado" if imagem_ref.startswith(LOCAL_MEDIA_PREFIX) else "URL"
        await ctx.send(f"✅ Imagem/GIF individual de `{potencial['potencial']}` configurado via {origem}.")

    @commands.command(help="(Admin) Seta um potencial para um player.")
    @commands.has_permissions(administrator=True)
    async def setar_potencial(self, ctx, membro: discord.Member, *, nome: str):
        with get_connection() as conn:
            # Verifica se o potencial existe
            res_potencial = conn.execute('SELECT nome FROM potenciais WHERE LOWER(nome) = LOWER(?)', (nome,)).fetchone()
            if not res_potencial:
                return await ctx.send("❌ Potencial não encontrado no sistema.")
            nome = res_potencial[0]
            
            # Verifica slots do personagem
            res_slots = conn.execute('SELECT slots_potencial FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
            if not res_slots:
                return await ctx.send("❌ O membro não possui um personagem.")
            
            possui = conn.execute('SELECT COUNT(*) FROM player_potencial WHERE user_id = ?', (membro.id,)).fetchone()[0]
            if possui >= res_slots[0]:
                return await ctx.send(f"❌ {membro.mention} já atingiu o limite de {res_slots[0]} slot(s).")

            try:
                conn.execute('INSERT INTO player_potencial (user_id, potencial) VALUES (?, ?)', (membro.id, nome))
                conn.commit()
                await ctx.send(f"✅ Potencial `{nome}` atribuído a {membro.mention}.")
            except:
                await ctx.send(f"❌ {membro.mention} já possui este potencial.")

    @commands.command(help="(Dono) Remove um potencial específico de um player.")
    @guild_owner_only()
    async def remover_potencial(self, ctx, membro: discord.Member, *, nome: str):
        with get_connection() as conn:
            conn.execute('DELETE FROM player_potencial WHERE user_id = ? AND potencial = ?', (membro.id, nome))
            conn.commit()
        await ctx.send(f"✅ Potencial `{nome}` removido de {membro.mention}.")

    @commands.command(help="(Admin) Dá slots extras de potencial a um player.")
    @commands.has_permissions(administrator=True)
    async def dar_slot_potencial(self, ctx, membro: discord.Member, qtd: int = 1):
        with get_connection() as conn:
            res = conn.execute('SELECT 1 FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
            if not res:
                return await ctx.send("❌ O membro não possui um personagem.")
            
            conn.execute('UPDATE personagens SET slots_potencial = slots_potencial + ? WHERE user_id = ?', (qtd, membro.id))
            conn.commit()
        await ctx.send(f"✅ {membro.mention} recebeu +{qtd} slot(s) de potencial.")

    @commands.command(
        name="ajustar_potencial",
        help="(Admin) Ajusta valores individuais. Uso: .ajustar_potencial @membro Shikai <mult|dur|cd> valor",
    )
    @commands.has_permissions(administrator=True)
    async def ajustar_potencial(self, ctx, membro: discord.Member, *, ajuste: str):
        try:
            partes = shlex.split(ajuste)
        except ValueError:
            return await ctx.send('❌ Não entendi o ajuste. Use: `.ajustar_potencial @membro "Shikai" mult 3.0`.')

        if len(partes) < 3:
            return await ctx.send('❌ Use: `.ajustar_potencial @membro "Shikai" <mult|dur|cd> valor`.')

        nome = " ".join(partes[:-2])
        campo = partes[-2]
        try:
            valor = float(partes[-1])
        except ValueError:
            return await ctx.send("❌ Valor inválido. Use números como `3.0`, `2`, `-1`.")

        campo = campo.lower().strip()
        aliases = {
            "mult": "mult_override",
            "multiplicador": "mult_override",
            "m": "mult_override",
            "dur": "dur_mod",
            "duracao": "dur_mod",
            "duração": "dur_mod",
            "d": "dur_mod",
            "cd": "cd_mod",
            "cooldown": "cd_mod",
            "recarga": "cd_mod",
            "c": "cd_mod",
        }
        coluna = aliases.get(campo)
        if not coluna:
            return await ctx.send("❌ Campo inválido. Use `mult`, `dur` ou `cd`.")

        if coluna in ("dur_mod", "cd_mod"):
            valor = int(valor)
        elif valor < 0:
            return await ctx.send("❌ O multiplicador individual não pode ser negativo.")

        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            potencial = conn.execute(
                """
                SELECT pp.potencial, p.multiplicador, p.duracao, p.cooldown
                FROM player_potencial pp
                JOIN potenciais p ON pp.potencial = p.nome
                WHERE pp.user_id = ? AND LOWER(pp.potencial) = LOWER(?)
                """,
                (membro.id, nome),
            ).fetchone()
            if not potencial:
                return await ctx.send(f"❌ {membro.mention} não possui o potencial `{nome}`.")

            conn.execute(
                f"UPDATE player_potencial SET {coluna} = ? WHERE user_id = ? AND potencial = ?",
                (valor, membro.id, potencial["potencial"]),
            )
            conn.commit()

        if coluna == "mult_override":
            detalhe = f"multiplicador individual `x{valor}`"
        elif coluna == "dur_mod":
            total = max(1, (potencial["duracao"] or 0) + valor)
            detalhe = f"modificador de duração `{valor:+d}` turno(s), total `{total}`"
        else:
            total = max(0, (potencial["cooldown"] or 0) + valor)
            detalhe = f"modificador de cooldown `{valor:+d}` turno(s), total `{total}`"

        await ctx.send(f"✅ `{potencial['potencial']}` de {membro.mention} ajustado: {detalhe}.")

    @commands.command(help="(Dono) Remove slots de potencial de um player.")
    @guild_owner_only()
    async def remover_slot_potencial(self, ctx, membro: discord.Member, qtd: int = 1):
        with get_connection() as conn:
            res = conn.execute('SELECT slots_potencial FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
            if not res:
                return await ctx.send("❌ O membro não possui um personagem.")
            
            novo_valor = max(1, res[0] - qtd)
            conn.execute('UPDATE personagens SET slots_potencial = ? WHERE user_id = ?', (novo_valor, membro.id))
            conn.commit()
        await ctx.send(f"✅ Slots de {membro.mention} ajustados para {novo_valor}.")

    @commands.command(name="restaura_cd", help="(Admin) Zera cooldowns ativos de Kidō, técnicas e potenciais de um jogador.")
    @commands.has_permissions(administrator=True)
    async def restaura_cd(self, ctx, membro: discord.Member):
        with get_connection() as conn:
            char = conn.execute("SELECT 1 FROM personagens WHERE user_id = ?", (membro.id,)).fetchone()
            if not char:
                return await ctx.send("❌ O membro não possui um personagem.")

            pot_rows = conn.execute(
                "UPDATE player_potencial SET cooldown = 0 WHERE user_id = ? AND cooldown > 0",
                (membro.id,),
            ).rowcount
            kido_rows = conn.execute(
                "UPDATE kido_estado SET cooldown = 0 WHERE user_id = ? AND cooldown > 0",
                (membro.id,),
            ).rowcount
            tecnica_rows = conn.execute(
                "UPDATE tecnica_estado SET cooldown = 0 WHERE user_id = ? AND cooldown > 0",
                (membro.id,),
            ).rowcount
            conn.commit()

        total = pot_rows + kido_rows + tecnica_rows
        if total == 0:
            return await ctx.send(f"✅ {membro.mention} não tinha cooldowns ativos.")
        await ctx.send(
            f"✅ Cooldowns zerados para {membro.mention}. "
            f"Potenciais: `{pot_rows}` | Kidō: `{kido_rows}` | Técnicas: `{tecnica_rows}`."
        )

    @commands.command(name="listar_potenciais", hidden=True)
    @commands.has_permissions(administrator=True)
    async def list_all(self, ctx):
        """Lista técnica de todos os potenciais criados."""
        with get_connection() as conn:
            pots = conn.execute('SELECT nome, multiplicador, duracao, cooldown, custo_ativacao, custo_turno FROM potenciais').fetchall()
        
        if not pots: return await ctx.send("❌ Nenhum potencial no banco.")
        
        embeds = []
        current = discord.Embed(title="📋 Todos os Potenciais do Sistema", color=0x2c3e50)
        for p in pots:
            if len(current.fields) == 10:
                embeds.append(current)
                current = discord.Embed(title="📋 Todos os Potenciais (cont.)", color=0x2c3e50)
            current.add_field(
                name=p[0],
                value=f"Mult: `{p[1]}` | Dur: `{p[2]}t` | CD: `{p[3]}t` | Reiryoku: `{p[4] or 0}/{p[5] or 0}`",
                inline=False,
            )
        
        embeds.append(current)
        if len(embeds) > 1:
            await ctx.send(embed=embeds[0], view=PaginatorView(embeds))
        else:
            await ctx.send(embed=embeds[0])

async def setup(bot):
    await bot.add_cog(PotencialSystem(bot))
