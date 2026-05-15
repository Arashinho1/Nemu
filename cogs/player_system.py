import discord
from discord.ext import commands
from discord import ui
from database import get_connection, get_vagas_bonus, get_canal_logs, get_pericia_bonuses
from utils.logic import (
    REIATSU_LIMITS,
    SPIRITUAL_POWER_LEVELS,
    format_reiatsu_limit,
    get_potencial_info,
    calcular_reiatsu,
    nivel_reiatsu,
    atribuir_vaga_logica,
    calcular_reiryoku,
)
from renderers.attribute_panel import render_attribute_panel_desktop, render_attribute_panel_mobile
from utils.avatar import read_discord_avatar
from utils.history_log import send_points_history
from utils.profile_service import distribute_attribute, get_profile_data
from utils.pericia_card import create_pericia_card
from utils.pericia_service import investir_pericia


class ModalDistribuir(ui.Modal, title='Distribuir Pontos'):
    quantidade = ui.TextInput(label='Quantidade')
    def __init__(self, user_id, atributo, nome_attr, profile_message=None, profile_layout="desktop"):
        super().__init__()
        self.user_id = user_id
        self.atributo, self.nome_attr = atributo, nome_attr
        self.profile_message = profile_message
        self.profile_layout = profile_layout
    async def on_submit(self, interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Você só pode distribuir pontos do seu próprio personagem.", ephemeral=True)
        try: qtd = int(self.quantidade.value)
        except: return await interaction.response.send_message("❌ Valor inválido.", ephemeral=True)
        if qtd <= 0: return await interaction.response.send_message("❌ A quantidade deve ser maior que zero.", ephemeral=True)

        ok, msg, details = distribute_attribute(self.user_id, self.atributo, qtd, return_details=True)
        if self.profile_message:
            file, embed = await build_profile_image_embed(self.user_id, interaction.user, self.profile_layout)
            if file:
                try:
                    await self.profile_message.edit(embed=embed, attachments=[file], view=PerfilView(self.user_id, self.profile_layout))
                except discord.DiscordException:
                    pass
        if ok:
            await send_points_history(
                interaction.client,
                action="Distribuição",
                point_type="Pontos de Atributos (PA)",
                quantity=qtd,
                giver=interaction.user,
                receiver=interaction.user,
                source_channel=interaction.channel,
                details=details,
            )
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)

class PerfilView(ui.View):
    def __init__(self, user_id, layout="desktop"):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.layout = layout

    async def _open_distribute_modal(self, interaction, atributo, nome_attr):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Você só pode distribuir pontos do seu próprio personagem.", ephemeral=True)
        await interaction.response.send_modal(ModalDistribuir(self.user_id, atributo, nome_attr, interaction.message, self.layout))

    @ui.button(label="𝗙𝗈𝗋𝖼̧𝖺", style=discord.ButtonStyle.secondary, row=0)
    async def add_forca(self, interaction, button):
        await self._open_distribute_modal(interaction, "forca", "Força")

    @ui.button(label="𝗩𝖾𝗅𝗈𝖼𝗂𝖽𝖺𝖽𝖾", style=discord.ButtonStyle.secondary, row=0)
    async def add_velocidade(self, interaction, button):
        await self._open_distribute_modal(interaction, "velocidade", "Velocidade")

    @ui.button(label="𝗥𝖾𝗌𝗂𝗌𝗍𝖾̂𝗇𝖼𝗂𝖺", style=discord.ButtonStyle.secondary, row=0)
    async def add_resistencia(self, interaction, button):
        await self._open_distribute_modal(interaction, "resistencia", "Resistência")

    @ui.button(label="Atualizar", style=discord.ButtonStyle.secondary, row=0)
    async def atualizar(self, interaction, button):
        member = _resolve_member(interaction.client, interaction.guild, self.user_id)
        file, embed = await build_profile_image_embed(self.user_id, member, self.layout)
        if not file:
            return await interaction.response.send_message("❌ Personagem não encontrado.", ephemeral=True)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

    @ui.button(label="Perícias", style=discord.ButtonStyle.primary, row=1)
    async def pericias(self, interaction, button):
        file, embed, view = build_pericia_image_embed(self.user_id, page=0, profile_layout=self.layout)
        if not file:
            return await interaction.response.send_message("❌ Personagem não encontrado.", ephemeral=True)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=view)

    @ui.button(label="Kidō", style=discord.ButtonStyle.primary, row=1)
    async def kido(self, interaction, button):
        from cogs.kido_system import KIDO_ACCESS_ERROR, KidoMenuView, build_kido_image_embed

        member = _resolve_member(interaction.client, interaction.guild, self.user_id)
        file, embed = await build_kido_image_embed(self.user_id, member)
        if not file:
            if get_profile_data(self.user_id):
                return await interaction.response.send_message(KIDO_ACCESS_ERROR, ephemeral=True)
            return await interaction.response.send_message("❌ Personagem não encontrado.", ephemeral=True)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=KidoMenuView(self.user_id, interaction.client, from_profile=True, profile_layout=self.layout))

    @ui.button(label="Técnicas", style=discord.ButtonStyle.primary, row=1)
    async def tecnicas(self, interaction, button):
        from cogs.tecnica_system import TecnicaMenuView, build_tecnica_image_embed

        member = _resolve_member(interaction.client, interaction.guild, self.user_id)
        file, embed = await build_tecnica_image_embed(self.user_id, member)
        if not file:
            return await interaction.response.send_message("❌ Personagem não encontrado.", ephemeral=True)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=TecnicaMenuView(self.user_id, from_profile=True, profile_layout=self.layout))


class PericiaImageView(ui.View):
    def __init__(self, user_id, page=0, visible=None, profile_layout="desktop"):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.page = page
        self.visible = visible or []
        self.profile_layout = profile_layout
        self._sync_buttons()

    def _sync_buttons(self):
        for index, pericia in enumerate(self.visible[:3], start=1):
            if pericia["custo_proximo"] is None:
                continue
            button = ui.Button(label=f"Investir {index}", style=discord.ButtonStyle.success, row=1)
            button.callback = self.make_upgrade_callback(pericia)
            self.add_item(button)

    def make_upgrade_callback(self, pericia):
        async def callback(interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ Você não pode evoluir as perícias deste personagem.", ephemeral=True)
            await interaction.response.send_modal(ModalInvestirPericia(self.user_id, pericia["id"], pericia["nome"], self.page, self.profile_layout))
        return callback

    @ui.button(label="Voltar", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction, button):
        file, embed, view = build_pericia_image_embed(self.user_id, self.page - 1, self.profile_layout)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=view)

    @ui.button(label="Avançar", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction, button):
        file, embed, view = build_pericia_image_embed(self.user_id, self.page + 1, self.profile_layout)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=view)

    @ui.button(label="Atualizar", style=discord.ButtonStyle.secondary, row=0)
    async def refresh(self, interaction, button):
        file, embed, view = build_pericia_image_embed(self.user_id, self.page, self.profile_layout)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=view)

    @ui.button(label="Perfil", style=discord.ButtonStyle.primary, row=1)
    async def back_profile(self, interaction, button):
        member = _resolve_member(interaction.client, interaction.guild, self.user_id)
        file, embed = await build_profile_image_embed(self.user_id, member, self.profile_layout)
        if not file:
            return await interaction.response.send_message("❌ Personagem não encontrado.", ephemeral=True)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=PerfilView(self.user_id, self.profile_layout))

def _resolve_member(client, guild, user_id):
    if guild:
        member = guild.get_member(int(user_id))
        if member:
            return member
    return client.get_user(int(user_id)) if client else None


async def _read_avatar(member):
    return await read_discord_avatar(member, size=512)


async def build_profile_image_embed(user_id, member=None, layout="desktop"):
    profile = get_profile_data(user_id)
    if not profile:
        return None, None
    avatar = await _read_avatar(member)
    renderer = render_attribute_panel_mobile if layout == "mobile" else render_attribute_panel_desktop
    image = renderer(user_id, character_data=profile, avatar_bytes=avatar)
    if not image:
        return None, None

    suffix = "_m" if layout == "mobile" else ""
    filename = f"perfil_{user_id}{suffix}.png"
    file = discord.File(image, filename=filename)
    embed = discord.Embed(color=0x2b2d31)
    embed.set_image(url=f"attachment://{filename}")
    return file, embed

def build_pericia_image_embed(user_id, page=0, profile_layout="desktop"):
    image, resolved_page, visible = create_pericia_card(user_id, page)
    if not image:
        return None, None, None

    filename = f"pericias_{user_id}.png"
    file = discord.File(image, filename=filename)
    embed = discord.Embed(color=0x2b2d31)
    embed.set_image(url=f"attachment://{filename}")
    return file, embed, PericiaImageView(user_id, resolved_page, visible, profile_layout)


class ModalInvestirPericia(ui.Modal, title='Investir PP em Perícia'):
    quantidade = ui.TextInput(label='Quantidade de PP para investir')

    def __init__(self, user_id, pericia_id, pericia_nome, page, profile_layout="desktop"):
        super().__init__()
        self.user_id = user_id
        self.pericia_id = pericia_id
        self.pericia_nome = pericia_nome
        self.page = page
        self.profile_layout = profile_layout
        self.quantidade.placeholder = f"Ex: 10 em {pericia_nome}"

    async def on_submit(self, interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Você não pode evoluir as perícias deste personagem.", ephemeral=True)

        ok, msg, details = investir_pericia(self.user_id, self.pericia_id, self.quantidade.value, return_details=True)
        file, embed, view = build_pericia_image_embed(self.user_id, self.page, self.profile_layout)
        if ok:
            await send_points_history(
                interaction.client,
                action="Distribuição",
                point_type="Pontos de Perícia (PP)",
                quantity=int(self.quantidade.value),
                giver=interaction.user,
                receiver=interaction.user,
                source_channel=interaction.channel,
                details=details,
            )
        if file and interaction.message:
            await interaction.response.edit_message(embed=embed, attachments=[file], view=view)
            await interaction.followup.send(("✅ " if ok else "❌ ") + msg, ephemeral=True)
            return
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)

async def parse_limit_break_args(ctx, args):
    completo = False
    membro = ctx.author
    converter = commands.MemberConverter()

    for arg in args:
        if arg.lower() in ("completo", "completa", "full", "total"):
            completo = True
            continue

        try:
            membro = await converter.convert(ctx, arg)
        except commands.BadArgument:
            return None, None, f"❌ Não entendi `{arg}`. Use `.romper_limite [completo] [@membro]`."

    return completo, membro, None

def get_current_reiatsu_limit_index(user_id):
    with get_connection() as conn:
        res = conn.execute(
            "SELECT forca, velocidade, resistencia, limite_nivel FROM personagens WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not res:
            return None

    forca, velocidade, resistencia, limite_atual = res
    v_bonuses = get_vagas_bonus(user_id)
    per_bonuses = get_pericia_bonuses(user_id)
    reiryoku = calcular_reiryoku(
        forca + v_bonuses["forca"]["fixo"],
        velocidade + v_bonuses["velocidade"]["fixo"],
        resistencia + v_bonuses["resistencia"]["fixo"],
    )
    reiryoku = int(reiryoku * (1.0 + per_bonuses.get("reiryoku", 0.0)))
    multiplicador = 1.0 + v_bonuses["forca"]["mult"] + per_bonuses.get("forca", 0.0) + per_bonuses.get("reiatsu", 0.0)
    reiatsu = calcular_reiatsu(reiryoku, multiplicador)

    alvo_idx = len(REIATSU_LIMITS) - 1
    for idx, (_, teto) in enumerate(REIATSU_LIMITS):
        if reiatsu <= teto:
            alvo_idx = idx
            break

    return limite_atual, alvo_idx, reiatsu

def delete_player_data(conn, user_id, include_character=True):
    if include_character:
        conn.execute('DELETE FROM personagens WHERE user_id = ?', (user_id,))

    user_tables = [
        'player_vagas',
        'player_pericias',
        'player_potencial',
        'kido_estado',
        'kido_usos',
        'tecnica_estado',
        'tecnica_usos',
        'tecnica_user_unlocks',
        'attribute_modifiers',
    ]
    for table in user_tables:
        conn.execute(f'DELETE FROM {table} WHERE user_id = ?', (user_id,))

    conn.execute('DELETE FROM kido_tecnicas WHERE classificacao = ? AND criador_id = ?', ('criado', user_id))
    conn.execute('DELETE FROM tecnicas WHERE classificacao = ? AND criador_id = ?', ('criado', user_id))

class ModalNome(ui.Modal, title='Registro'):
    nome_input = ui.TextInput(label='Nome do Personagem')
    def __init__(self, raca):
        super().__init__()
        self.raca = raca
    async def on_submit(self, interaction):
        with get_connection() as conn:
            try:
                existing = conn.execute('SELECT 1 FROM personagens WHERE user_id = ?', (interaction.user.id,)).fetchone()
                if existing:
                    return await interaction.response.send_message("❌ Você já possui personagem.", ephemeral=True)

                delete_player_data(conn, interaction.user.id, include_character=False)
                conn.execute('INSERT INTO personagens (user_id, nome, raca) VALUES (?, ?, ?)', (interaction.user.id, self.nome_input.value, self.raca))
                conn.commit()
            except:
                return await interaction.response.send_message("❌ Não foi possível criar o personagem.", ephemeral=True)
        
        # Atribui a vaga/raça e cargos automaticamente após criar
        sucesso, msg = await atribuir_vaga_logica(interaction.guild, interaction.user, self.raca)
        await interaction.response.send_message(f"✅ Personagem criado como **{self.raca}**! {msg}", ephemeral=True)

class MenuRaca(ui.View):
    def __init__(self, races):
        super().__init__(timeout=None)
        for race in races:
            btn = ui.Button(label=race, style=discord.ButtonStyle.primary)
            btn.callback = self.make_callback(race)
            self.add_item(btn)

    def make_callback(self, race_name):
        async def callback(interaction):
            await interaction.response.send_modal(ModalNome(race_name))
        return callback

class ConfirmDeleteView(ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=30)
        self.user_id = user_id

    @ui.button(label="Confirmar Exclusão", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Você não pode fazer isso.", ephemeral=True)
        
        with get_connection() as conn:
            delete_player_data(conn, self.user_id)
            conn.commit()
        
        await interaction.response.edit_message(content="🗑️ Sua ficha foi apagada permanentemente.", embed=None, view=None)

    @ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Ação cancelada.", embed=None, view=None)

class ConfirmResetPlayerView(ui.View):
    def __init__(self, requester_id, target):
        super().__init__(timeout=30)
        self.requester_id = requester_id
        self.target = target
        self.target_id = target.id
        self.target_mention = target.mention

    async def check_requester(self, interaction):
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message("❌ Apenas quem iniciou esta confirmação pode responder.", ephemeral=True)
        return False

    @ui.button(label="Resetar Jogador", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        if not await self.check_requester(interaction):
            return

        with get_connection() as conn:
            existing = conn.execute('SELECT nome FROM personagens WHERE user_id = ?', (self.target_id,)).fetchone()
            if not existing:
                return await interaction.response.edit_message(
                    content=f"❌ {self.target_mention} não possui personagem para resetar.",
                    embed=None,
                    view=None,
                )
            role_ids = [
                row[0]
                for row in conn.execute(
                    '''
                    SELECT v.role_id
                    FROM player_vagas pv
                    JOIN vagas v ON pv.vaga_nome = v.nome
                    WHERE pv.user_id = ? AND v.role_id IS NOT NULL
                    ''',
                    (self.target_id,),
                ).fetchall()
                if row[0]
            ]
            delete_player_data(conn, self.target_id)
            conn.commit()

        role_warning = ""
        roles = []
        if interaction.guild:
            for role_id in role_ids:
                role = interaction.guild.get_role(int(role_id))
                if role and role in self.target.roles:
                    roles.append(role)
        if roles:
            try:
                await self.target.remove_roles(
                    *roles,
                    reason=f"Reset de jogador solicitado por {interaction.user} ({interaction.user.id})",
                )
            except discord.DiscordException:
                role_warning = "\n⚠️ Não consegui remover um ou mais cargos no Discord. Confira as permissões/cargo do bot."

        await interaction.response.edit_message(
            content=(
                f"🧹 {self.target_mention} teve ficha, progresso, técnicas criadas e "
                f"desbloqueios individuais resetados.{role_warning}"
            ),
            embed=None,
            view=None,
        )

    @ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        if not await self.check_requester(interaction):
            return
        await interaction.response.edit_message(content="Ação cancelada.", embed=None, view=None)

class PlayerSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def perfil(self, ctx, *args):
        layout = "desktop"
        target = ctx.author
        converter = commands.MemberConverter()

        for arg in args:
            if arg.lower() in ("m", "mobile", "celular"):
                layout = "mobile"
                continue
            if arg.lower() in ("pc", "desktop"):
                layout = "desktop"
                continue
            try:
                target = await converter.convert(ctx, arg)
            except commands.BadArgument:
                return await ctx.send("❌ Use `.perfil`, `.perfil m`, `.perfil @membro` ou `.perfil m @membro`.")

        file, embed = await build_profile_image_embed(target.id, target, layout)
        if not embed: return await ctx.send("❌ Personagem não encontrado.")
        await ctx.send(file=file, embed=embed, view=PerfilView(target.id, layout))

    @commands.command()
    async def deletar(self, ctx):
        """Apaga permanentemente sua ficha de personagem."""
        embed = discord.Embed(
            title="⚠️ Aviso Crítico",
            description="Você está prestes a apagar sua ficha, níveis, passivas e conquistas. Esta ação **não pode ser desfeita**.\n\nDeseja continuar?",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed, view=ConfirmDeleteView(ctx.author.id))

    @commands.command(name="resetar", help="(Admin) Reseta a ficha e progresso de um jogador. Uso: .resetar @membro")
    @commands.has_permissions(administrator=True)
    async def resetar(self, ctx, membro: discord.Member = None):
        if not membro:
            return await ctx.send("❌ Use `.resetar @membro`.")
        if membro.bot:
            return await ctx.send("❌ Informe um jogador, não um bot.")

        with get_connection() as conn:
            personagem = conn.execute(
                'SELECT nome, raca FROM personagens WHERE user_id = ?',
                (membro.id,),
            ).fetchone()

        if not personagem:
            return await ctx.send(f"❌ {membro.mention} não possui personagem para resetar.")

        nome, raca = personagem
        embed = discord.Embed(
            title="⚠️ Resetar Jogador",
            description=(
                f"Você está prestes a apagar a ficha e o progresso de {membro.mention}.\n\n"
                f"Personagem: **{nome}**\n"
                f"Raça: **{raca}**\n\n"
                "Também serão removidos vagas atribuídas, perícias, potenciais, cooldowns, "
                "técnicas/Kidō criados e desbloqueios individuais."
            ),
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed, view=ConfirmResetPlayerView(ctx.author.id, membro))

    @commands.command()
    async def criar(self, ctx):
        with get_connection() as conn:
            races = [row[0] for row in conn.execute('SELECT nome FROM vagas WHERE categoria = "Raças Iniciais"').fetchall()]
        
        if not races:
            return await ctx.send("❌ Nenhuma raça inicial configurada. Use `.inicial` para adicionar.")
            
        await ctx.send("Escolha sua raça inicial:", view=MenuRaca(races))

    @commands.command(help="(Admin) Dá pontos para um jogador. Uso: .dar <pa|pp> <membro> <valor>")
    @commands.has_permissions(administrator=True)
    async def dar(self, ctx, tipo: str, membro: discord.Member, valor: int):
        coluna = "pontos_livres" if tipo.lower() == "pa" else "pontos_pericia" if tipo.lower() == "pp" else None
        if not coluna:
            return await ctx.send("❌ Tipo inválido. Use `pa` (Atributos) ou `pp` (Perícia).")
            
        with get_connection() as conn:
            res = conn.execute(f'SELECT {coluna} FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
            if not res:
                return await ctx.send("❌ Personagem não encontrado.")
            conn.execute(f'UPDATE personagens SET {coluna} = {coluna} + ? WHERE user_id = ?', (valor, membro.id))
            conn.commit()
        
        label = "Pontos de Atributos (PA)" if tipo.lower() == "pa" else "Pontos de Perícia (PP)"
        await send_points_history(
            self.bot,
            action="Recebimento",
            point_type=label,
            quantity=valor,
            giver=ctx.author,
            receiver=membro,
            source_channel=ctx.channel,
            details={
                "pool_label": "Saldo",
                "pool_before": res[0],
                "pool_after": res[0] + valor,
            },
        )
        await ctx.send(f"💎 {membro.mention} recebeu {valor} {label}.")

    @commands.command(help="(Admin) Seta o nível de Reiatsu de um player, dando pontos livres proporcionais.")
    @commands.has_permissions(administrator=True)
    async def setar_nivel(self, ctx, membro: discord.Member, *, nivel: str):
        niveis = {
            nome.lower(): (idx, nome, minimo, maximo)
            for idx, (nome, minimo, maximo) in enumerate(SPIRITUAL_POWER_LEVELS)
        }
        alvo = nivel.lower()
        if alvo not in niveis:
            return await ctx.send(
                f"❌ Nível inválido! Use: `{', '.join(niveis.keys())}`"
            )
        alvo_idx, target_nome, target_reiatsu, target_cap = niveis[alvo]

        with get_connection() as conn:
            res = conn.execute('SELECT raca, forca, velocidade, resistencia, limite_nivel, pontos_livres FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
            if not res:
                return await ctx.send("❌ Personagem não encontrado.")

            raca, f, v, r, limite_atual, pontos_livres_atual = res
            v_bonuses = get_vagas_bonus(membro.id)
            fator = 1.0 + v_bonuses['forca']['mult']
            
            reiryoku_necessario = target_reiatsu / fator
            reiryoku_atual = (f + v_bonuses['forca']['fixo']) + (v + v_bonuses['velocidade']['fixo']) + (r + v_bonuses['resistencia']['fixo'])
            
            pontos_para_dar = int(reiryoku_necessario - reiryoku_atual)
            if pontos_para_dar <= 0:
                return await ctx.send(f"⚠️ {membro.mention} já possui poder superior ao nível **{target_nome}**.")

            conn.execute('UPDATE personagens SET pontos_livres = pontos_livres + ?, limite_nivel = ? WHERE user_id = ?', 
                           (pontos_para_dar, max(limite_atual, alvo_idx), membro.id))
            conn.commit()
        await send_points_history(
            self.bot,
            action="Recebimento",
            point_type="Pontos de Atributos (PA)",
            quantity=pontos_para_dar,
            giver=ctx.author,
            receiver=membro,
            source_channel=ctx.channel,
            details={
                "pool_label": "PA disponíveis",
                "pool_before": pontos_livres_atual,
                "pool_after": pontos_livres_atual + pontos_para_dar,
                "extra": f"Origem: setar nível para {target_nome}",
            },
        )
        await ctx.send(
            f"📈 {membro.mention} recebeu `{pontos_para_dar}` pontos para entrar no nível "
            f"**{target_nome}** (`{format_reiatsu_limit(target_reiatsu)}` a `{format_reiatsu_limit(target_cap)}`)."
        )

    @commands.command(help="(Admin) Rompe o limite de um player. Use `.romper_limite completo @membro` para sincronizar com a Reiatsu atual.")
    @commands.has_permissions(administrator=True)
    async def romper_limite(self, ctx, *args):
        completo, membro, erro = await parse_limit_break_args(ctx, args)
        if erro:
            return await ctx.send(erro)
        if completo:
            return await self.aplicar_romper_limite_completo(ctx, membro)

        with get_connection() as conn:
            res = conn.execute('SELECT limite_nivel FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
            if not res:
                return await ctx.send("❌ Personagem não encontrado.")
            
            novo_limite = res[0] + 1
            if novo_limite >= len(REIATSU_LIMITS):
                return await ctx.send("🌌 Limite máximo absoluto já alcançado!")

            conn.execute('UPDATE personagens SET limite_nivel = ? WHERE user_id = ?', (novo_limite, membro.id))
            conn.commit()
        await ctx.send(f"✨ **LIMIT BREAK!** {membro.mention} agora pode alcançar o nível **{REIATSU_LIMITS[novo_limite][0]}**!")

    @commands.command(name="romper_limite_completo", help="(Admin) Ajusta o limite do player diretamente para o nível da Reiatsu atual.")
    @commands.has_permissions(administrator=True)
    async def romper_limite_completo_cmd(self, ctx, membro: discord.Member = None):
        await self.aplicar_romper_limite_completo(ctx, membro or ctx.author)

    async def aplicar_romper_limite_completo(self, ctx, membro):
        dados = get_current_reiatsu_limit_index(membro.id)
        if not dados:
            return await ctx.send("❌ Personagem não encontrado.")

        limite_atual, limite_alvo, reiatsu = dados
        limite_atual = min(limite_atual, len(REIATSU_LIMITS) - 1)
        if limite_alvo <= limite_atual:
            return await ctx.send(
                f"✅ {membro.mention} já está compatível com a Reiatsu atual.\n"
                f"Reiatsu: `{reiatsu}` | Limite: **{REIATSU_LIMITS[limite_atual][0]}**."
            )

        with get_connection() as conn:
            conn.execute("UPDATE personagens SET limite_nivel = ? WHERE user_id = ?", (limite_alvo, membro.id))
            conn.commit()

        await ctx.send(
            f"✨ **LIMIT BREAK COMPLETO!** {membro.mention} foi ajustado de "
            f"**{REIATSU_LIMITS[limite_atual][0]}** para **{REIATSU_LIMITS[limite_alvo][0]}**.\n"
            f"Reiatsu atual: `{reiatsu}` | Novo teto: `{format_reiatsu_limit(REIATSU_LIMITS[limite_alvo][1])}`."
        )

    @commands.command(help="Lista todos os buffs, bônus e multiplicadores ativos no seu personagem.")
    async def buffs(self, ctx):
        user_id = ctx.author.id
        with get_connection() as conn:
            char = conn.execute('SELECT 1 FROM personagens WHERE user_id = ?', (user_id,)).fetchone()
            if not char:
                return await ctx.send("❌ Você não possui um personagem para ver buffs.")

        v_bonuses = get_vagas_bonus(user_id)
        p_bonuses = get_pericia_bonuses(user_id)
        mult_pot, pot_nome, ativo = get_potencial_info(user_id)
        manual_by_attr = {
            attr: {"flat": 0.0, "percent": 0.0, "multiplier": 1.0, "lines": []}
            for attr in ["forca", "velocidade", "resistencia"]
        }

        embed = discord.Embed(title="✨ Buffs & Atributos Ativos", color=0xf1c40f)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        if ativo:
            embed.add_field(name="🔥 Liberação Ativa", value=f"**{pot_nome}**\nMultiplicador: `x{mult_pot:.2f}`", inline=False)

        vagas_buffs = []
        with get_connection() as conn:
            res = conn.execute('''
                SELECT v.nome, v.multiplicador, v.bonus_fixo, v.atributo
                FROM player_vagas pv JOIN vagas v ON pv.vaga_nome = v.nome 
                WHERE pv.user_id = ?
            ''', (user_id,)).fetchall()
            for nome, mult, fixo, attr in res:
                if mult > 0 or fixo > 0:
                    vagas_buffs.append(f"• **{nome}**: `+{int(mult*100)}%` / `+{fixo}` ({attr})")

            manual_rows = conn.execute('''
                SELECT atributo, nome, tipo, valor, origem, turnos_restantes
                FROM attribute_modifiers
                WHERE user_id = ? AND ativo = 1
                ORDER BY origem COLLATE NOCASE, nome COLLATE NOCASE
            ''', (user_id,)).fetchall()
            for attr, nome, tipo, valor, origem, turnos in manual_rows:
                if attr not in manual_by_attr:
                    continue
                valor = float(valor or 0)
                if tipo == "percent":
                    manual_by_attr[attr]["percent"] += valor / 100
                    valor_text = f"+{valor:g}%"
                elif tipo == "multiplier":
                    manual_by_attr[attr]["multiplier"] *= valor
                    valor_text = f"x{valor:.2f}"
                else:
                    manual_by_attr[attr]["flat"] += valor
                    valor_text = f"+{int(valor)}"
                dur_text = f" | {turnos} turno(s)" if turnos is not None else ""
                manual_by_attr[attr]["lines"].append(
                    f"• **{nome}**: `{valor_text}` em {attr} ({origem or 'manual'}{dur_text})"
                )

        if vagas_buffs:
            embed.add_field(name="📜 Bônus de Vagas & Títulos", value="\n".join(vagas_buffs), inline=False)

        pericia_buffs = [f"• **{k.capitalize()}**: `+{int(v*100)}%`" for k, v in p_bonuses.items() if v > 0]
        if pericia_buffs:
            embed.add_field(name="📊 Bônus de Perícias", value="\n".join(pericia_buffs), inline=False)

        temp_buffs = []
        for attr in ["forca", "velocidade", "resistencia"]:
            temp_buffs.extend(manual_by_attr[attr]["lines"])
        if temp_buffs:
            embed.add_field(name="⚔️ Bônus Temporários", value="\n".join(temp_buffs[:12]), inline=False)

        resumo = ""
        for attr in ['forca', 'velocidade', 'resistencia']:
            manual = manual_by_attr[attr]
            m_total = (1.0 + v_bonuses[attr]['mult'] + p_bonuses[attr] + manual["percent"]) * mult_pot * manual["multiplier"]
            fixo_text = f" | Fixo temp: `+{int(manual['flat'])}`" if manual["flat"] else ""
            resumo += f"┣ **{attr.capitalize()}**: `x{m_total:.2f}`{fixo_text}\n"
        
        embed.add_field(name="🎯 Multiplicadores Finais", value=resumo + "┗ *Cálculo: (Base + Vagas + Perícias) * Liberação*", inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(PlayerSystem(bot))
