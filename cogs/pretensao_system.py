import discord
from discord.ext import commands, tasks
from discord import ui
import database
from utils import logic
import sqlite3

DIAS_LABELS = {"0": "Seg", "1": "Ter", "2": "Qua", "3": "Qui", "4": "Sex", "5": "Sab", "6": "Dom"}


def formatar_dias(lista_dias):
    dias_validos = [DIAS_LABELS[dia] for dia in sorted(lista_dias or []) if dia in DIAS_LABELS]
    return ", ".join(dias_validos) if dias_validos else "Nenhum"


def janela_oficial_aberta(config):
    return logic.esta_na_janela_pretensao((
        config["canal_id"],
        config["hora_abrir"],
        config["hora_fechar"],
        config["dias_semana"],
    ))


def pretensao_ativa(config):
    return janela_oficial_aberta(config) and not bool(config["fechado_manual"])


def build_resumo_vagas_embed():
    with database.get_connection() as conn:
        conn.row_factory = sqlite3.Row
        vagas = conn.execute('''
            SELECT v.nome, v.categoria, v.limite, v.bloqueada, COUNT(pv.user_id) AS ocupantes
            FROM vagas v
            LEFT JOIN player_vagas pv ON pv.vaga_nome = v.nome
            WHERE v.categoria IS NOT NULL AND v.categoria != ''
            GROUP BY v.nome
            ORDER BY v.categoria COLLATE NOCASE, v.nome COLLATE NOCASE
        ''').fetchall()

    embed = discord.Embed(
        title="📊 Vagas disponíveis por categoria",
        color=0x2ecc71
    )

    if not vagas:
        embed.description = "Nenhuma vaga cadastrada."
        return embed

    resumo = {}
    for vaga in vagas:
        categoria = vaga["categoria"] or "Sem categoria"
        dados = resumo.setdefault(categoria, {
            "total": 0,
            "disponiveis": 0,
            "slots_livres": 0,
            "ilimitadas": 0,
            "bloqueadas": 0,
        })
        dados["total"] += 1

        if vaga["bloqueada"]:
            dados["bloqueadas"] += 1
            continue

        limite = int(vaga["limite"] or 0)
        ocupantes = int(vaga["ocupantes"] or 0)

        if limite <= 0:
            dados["disponiveis"] += 1
            dados["ilimitadas"] += 1
            continue

        livres = max(limite - ocupantes, 0)
        if livres > 0:
            dados["disponiveis"] += 1
            dados["slots_livres"] += livres

    for categoria, dados in list(resumo.items())[:25]:
        linhas = [f"Disponíveis: `{dados['disponiveis']}/{dados['total']}` vagas"]
        if dados["slots_livres"]:
            linhas.append(f"Slots livres: `{dados['slots_livres']}`")
        if dados["ilimitadas"]:
            linhas.append(f"Ilimitadas: `{dados['ilimitadas']}`")
        if dados["bloqueadas"]:
            linhas.append(f"Bloqueadas: `{dados['bloqueadas']}`")
        embed.add_field(name=categoria, value="\n".join(linhas), inline=True)

    return embed


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

class PretensaoTimeModal(ui.Modal, title="Configurar Horários"):
    abrir = ui.TextInput(label="Hora de Abertura (HH:MM)", placeholder="Ex: 19:00", min_length=5, max_length=5)
    fechar = ui.TextInput(label="Hora de Fechamento (HH:MM)", placeholder="Ex: 22:00", min_length=5, max_length=5)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        if ":" not in self.abrir.value or ":" not in self.fechar.value:
            return await interaction.response.send_message("❌ Formato inválido. Use HH:MM.", ephemeral=True)
        
        self.parent_view.hora_abrir = self.abrir.value
        self.parent_view.hora_fechar = self.fechar.value
        await self.parent_view.atualizar_mensagem(interaction)

class DiasSemanaSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Segunda", value="0"),
            discord.SelectOption(label="Terça", value="1"),
            discord.SelectOption(label="Quarta", value="2"),
            discord.SelectOption(label="Quinta", value="3"),
            discord.SelectOption(label="Sexta", value="4"),
            discord.SelectOption(label="Sábado", value="5"),
            discord.SelectOption(label="Domingo", value="6"),
        ]
        super().__init__(
            placeholder="Selecione os dias da semana...",
            min_values=1,
            max_values=7,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.dias_selecionados = self.values
        await self.view.atualizar_mensagem(interaction)

class PretensaoSetupView(ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.hora_abrir = "19:00"
        self.hora_fechar = "22:00"
        self.dias_selecionados = ["0", "1", "2", "3", "4", "5", "6"]
        config = database.get_config_pretensao()
        if config:
            _, hora_abrir, hora_fechar, dias_semana = config
            self.hora_abrir = hora_abrir or self.hora_abrir
            self.hora_fechar = hora_fechar or self.hora_fechar
            self.dias_selecionados = [
                dia.strip() for dia in str(dias_semana or "").split(",") if dia.strip()
            ]
        self.add_item(DiasSemanaSelect())

    def _formatar_dias(self, lista_dias):
        return formatar_dias(lista_dias)

    def build_embed(self):
        embed = discord.Embed(title="⚙️ Configuração de Pretensão", color=0x7289da)
        embed.description = "Use o menu suspenso para os dias e o botão para os horários."
        embed.add_field(name="Abertura", value=f"`{self.hora_abrir}`", inline=True)
        embed.add_field(name="Fechamento", value=f"`{self.hora_fechar}`", inline=True)
        embed.add_field(name="Dias Ativos", value=f"`{self._formatar_dias(self.dias_selecionados)}`", inline=False)
        return embed

    async def atualizar_mensagem(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @ui.button(label="Definir Horários", style=discord.ButtonStyle.secondary)
    async def definir_horas(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Apenas quem usou o comando pode configurar.", ephemeral=True)
        await interaction.response.send_modal(PretensaoTimeModal(self))

    @ui.button(label="💾 Salvar Configuração", style=discord.ButtonStyle.success)
    async def salvar(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        if not self.dias_selecionados:
            return await interaction.response.send_message("❌ Selecione pelo menos um dia antes de salvar.", ephemeral=True)
        
        dias_str = ",".join(sorted(self.dias_selecionados))
        database.set_config_pretensao_horarios(self.hora_abrir, self.hora_fechar, dias_str)
        
        await interaction.response.edit_message(
            content="✅ **Configuração de Pretensão salva com sucesso!**",
            embed=self.build_embed(),
            view=None
        )

    @ui.button(label="Cancelar Pretensão", style=discord.ButtonStyle.danger)
    async def cancelar(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

        config = database.get_config_pretensao()
        database.cancelar_config_pretensao()

        await interaction.response.defer()
        if config and config[0] and interaction.guild:
            canal = interaction.guild.get_channel(config[0]) or interaction.client.get_channel(config[0])
            if canal:
                perms = canal.overwrites_for(canal.guild.default_role)
                if perms.send_messages is not False:
                    perms.send_messages = False
                    await canal.set_permissions(canal.guild.default_role, overwrite=perms)

        await interaction.edit_original_response(
            content="⛔ **Pretensão cancelada.** A agenda foi desativada e o canal configurado foi silenciado.",
            embed=None,
            view=None
        )

class PretensaoSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.verificador_pretensao.start()

    def cog_unload(self):
        self.verificador_pretensao.cancel()

    async def _aplicar_permissao_pretensao(self, canal, aberto):
        perms = canal.overwrites_for(canal.guild.default_role)
        if perms.send_messages != aberto:
            perms.send_messages = aberto
            await canal.set_permissions(canal.guild.default_role, overwrite=perms)

    def _buscar_config_pretensao(self):
        with database.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute('''
                SELECT canal_id, hora_abrir, hora_fechar, dias_semana, anunciado, fechado_manual
                FROM config_pretensao
                WHERE id = 1
            ''').fetchone()

    @commands.command(name="criar_pretensão")
    @commands.has_permissions(administrator=True)
    async def criar_pretensao(self, ctx, canal: discord.TextChannel = None):
        """Define o canal onde a pretensão irá ocorrer."""
        target = canal or ctx.channel
        database.set_config_pretensao_canal(target.id)
        await ctx.send(f"🎯 Canal de Pretensão definido para {target.mention}.")

    @commands.command(name="setar_pretensão")
    @commands.has_permissions(administrator=True)
    async def setar_pretensao_cmd(self, ctx, abrir: str = None, fechar: str = None, dias: str = "0,1,2,3,4,5,6"):
        """Configura o horário e dias da pretensão. Se usado sem argumentos, abre o menu visual."""
        if abrir is None:
            view = PretensaoSetupView(ctx.author.id)
            return await ctx.send(embed=view.build_embed(), view=view)

        # Mantém compatibilidade com comando direto
        if fechar is None:
            return await ctx.send("❌ Informe abertura e fechamento. Ex: `.setar_pretensão 19:00 22:00`")
        if ":" not in abrir or ":" not in fechar:
            return await ctx.send("❌ Formato de hora inválido. Use HH:MM.")

        database.set_config_pretensao_horarios(abrir, fechar, dias)
        
        dias_formatados = dias.replace("0","Seg").replace("1","Ter").replace("2","Qua").replace("3","Qui").replace("4","Sex").replace("5","Sab").replace("6","Dom")
        await ctx.send(f"🕒 **Configuração Atualizada!**\nAbertura: `{abrir}` | Fechamento: `{fechar}`\nDias: `{dias_formatados}`")

    @commands.command(name="fechar_pretensão")
    @commands.has_permissions(administrator=True)
    async def fechar_pretensao_cmd(self, ctx):
        """Fecha a pretensão antes do horário oficial de término."""
        config = self._buscar_config_pretensao()
        if not config or not config["canal_id"]:
            return await ctx.send("❌ O canal de pretensão ainda não foi configurado. Use `.criar_pretensão #canal`.")

        canal = self.bot.get_channel(config["canal_id"]) or ctx.guild.get_channel(config["canal_id"])
        if not canal:
            return await ctx.send("❌ Não encontrei o canal configurado para a pretensão.")

        if not janela_oficial_aberta(config):
            await self._aplicar_permissao_pretensao(canal, False)
            database.set_pretensao_fechado_manual(False)
            return await ctx.send("🔒 A pretensão já estava fora do horário oficial. O canal configurado foi silenciado.")

        database.set_pretensao_fechado_manual(True)
        await self._aplicar_permissao_pretensao(canal, False)
        mensagem = "🔒 **Sistema de Pretensão Encerrado pela Staff.** O chat foi silenciado antes do horário oficial."

        if canal.id == ctx.channel.id:
            await ctx.send(mensagem)
        else:
            await canal.send(mensagem)
            await ctx.send(f"🔒 Pretensão fechada antes do horário oficial em {canal.mention}.")

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
        config = self._buscar_config_pretensao()
        
        if not config or not config['canal_id']: return
        canal = self.bot.get_channel(config['canal_id'])
        if not canal: return
        
        aberta_no_horario = janela_oficial_aberta(config)
        fechado_manual = bool(config['fechado_manual'])
        if not aberta_no_horario and fechado_manual:
            database.set_pretensao_fechado_manual(False)
            fechado_manual = False

        deve_abrir = aberta_no_horario and not fechado_manual
        
        await self._aplicar_permissao_pretensao(canal, deve_abrir)

        if deve_abrir and not config['anunciado']:
            # Anuncio Inicial
            await canal.send(
                f"📢 @everyone **O SISTEMA DE PRETENSÃO COMEÇOU!** 🔓\nMandem o ID da vaga desejada abaixo.",
                embed=build_resumo_vagas_embed()
            )
            # Envia o comando .vagas automaticamente
            vagas_cmd = self.bot.get_command("vagas")
            ctx = await self.bot.get_context(await canal.send("⌛ Carregando lista de vagas..."))
            await ctx.invoke(vagas_cmd)
            
            with database.get_connection() as conn:
                conn.execute("UPDATE config_pretensao SET anunciado = 1, fechado_manual = 0 WHERE id = 1")
                conn.commit()
        elif not aberta_no_horario and config['anunciado']:
            await canal.send("🔒 **Sistema de Pretensão Encerrado.** O chat foi silenciado.")
            with database.get_connection() as conn:
                conn.execute("UPDATE config_pretensao SET anunciado = 0 WHERE id = 1")
                conn.commit()

    @commands.command(name="pretensão")
    async def pretensao_status(self, ctx):
        """Mostra o status atual e o cronograma da pretensão."""
        config = self._buscar_config_pretensao()
        if not config or not config["canal_id"]:
            return await ctx.send("❌ O sistema de pretensão ainda não foi configurado. Use `.criar_pretensão #canal` para definir o local e `.setar_pretensão` para os horários.")
        
        h_abrir = config["hora_abrir"]
        h_fechar = config["hora_fechar"]
        dias_str = config["dias_semana"]
        if not dias_str:
            return await ctx.send("🚦 **Status da Pretensão:** 🔴 **CANCELADA**\nUse `.setar_pretensão` para configurar uma nova agenda.")

        esta_aberto = pretensao_ativa(config)

        dias_formatados = formatar_dias([d for d in dias_str.split(",") if d])

        if esta_aberto:
            await ctx.send(f"🚦 **Status da Pretensão:** 🟢 **ABERTO**\n🕒 O chat será silenciado hoje às `{h_fechar}`.")
        elif janela_oficial_aberta(config) and config["fechado_manual"]:
            await ctx.send(
                f"🚦 **Status da Pretensão:** 🔴 **FECHADO PELA STAFF**\n"
                f"🕒 A janela oficial iria até `{h_fechar}`."
            )
        else:
            await ctx.send(
                f"🚦 **Status da Pretensão:** 🔴 **FECHADO**\n"
                f"🕒 Horário: `{h_abrir}` às `{h_fechar}`\n"
                f"📅 Dias ativos: `{dias_formatados}`"
            )

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        config = self._buscar_config_pretensao()

        if config and message.channel.id == config['canal_id']:
            if not pretensao_ativa(config):
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
                    if sucesso and msg == "✅ Sucesso":
                        await message.channel.send(f"{message.author.mention} pegou a vaga {vaga_res[0]}")
                    else:
                        await message.channel.send(f"{'✅' if sucesso else '❌'} {message.author.mention}: {msg}")

async def setup(bot):
    await bot.add_cog(PretensaoSystem(bot))
