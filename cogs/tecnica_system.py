import discord
import asyncio
from discord import ui
from discord.ext import commands

from database import get_connection
from utils.avatar import read_discord_avatar
from utils.profile_service import get_profile_data
from utils.tecnica_template import create_tecnica_card
from utils.tecnica_service import (
    CLASSIFICATION_LABELS,
    configure_tecnica_buff,
    create_tecnica,
    ensure_tecnica_state,
    format_targets,
    grant_tecnica_to_role,
    grant_tecnica_to_user,
    list_available_tecnicas,
    list_tecnicas,
    normalize_classification,
    use_tecnica,
)


CREATE_TYPE_LABELS = {
    "criado": "Técnica Criada",
    "oficial": "Técnica Oficial",
}
LIST_PER_PAGE = 6


def _resolve_member(client, guild, user_id):
    if guild:
        member = guild.get_member(int(user_id))
        if member:
            return member
    return client.get_user(int(user_id)) if client else None


def _member_role_ids(member):
    return [role.id for role in getattr(member, "roles", []) if getattr(role, "id", None)]


def _format_buff(tecnica):
    parts = []
    if tecnica.get("multiplicador"):
        parts.append(f"+{int(float(tecnica['multiplicador']) * 100)}%")
    if tecnica.get("bonus_fixo"):
        parts.append(f"+{int(tecnica['bonus_fixo'])}")
    return " / ".join(parts) if parts else "sem buff"


def _tecnica_status_label(tecnica, available_only=False):
    if tecnica.get("classificacao") != "oficial":
        return "Criada"
    if available_only:
        return "Disponível"
    return "Restrita" if int(tecnica.get("liberada") or 0) == 0 else "Liberada"


def _tecnica_list_rows(classificacao, user_id=None, include_private=False, available_only=False, role_ids=None):
    if available_only and user_id:
        return list_available_tecnicas(user_id, classificacao, role_ids)
    return list_tecnicas(classificacao, user_id=user_id, include_private=include_private)


def _extract_unlock_args(ctx, entrada):
    role = ctx.message.role_mentions[0] if ctx.message.role_mentions else None
    member = ctx.message.mentions[0] if ctx.message.mentions else None
    if role and member:
        return None, None, "", "Mencione apenas um alvo: cargo ou player."
    if not role and not member:
        return None, None, "", (
            "Mencione o cargo ou player no final do comando. "
            "Ex: `!setar_técnica Cero Oscuras @cargo` ou `!setar_técnica Cero Oscuras @player`."
        )

    target = role or member
    target_type = "role" if role else "user"
    nome = entrada or ""
    tokens = [target.mention, f"@{target.name}", target.name]
    if role:
        tokens.append(f"<@&{role.id}>")
    else:
        tokens.extend([f"<@{member.id}>", f"<@!{member.id}>", f"@{member.display_name}", member.display_name])
    for token in tokens:
        nome = nome.replace(token, " ")
    nome = " ".join(nome.split()).strip()
    if not nome:
        return None, None, "", "Informe o nome da técnica antes da menção."
    return target_type, target, nome, None


def build_tecnica_card_data(user_id, role_ids=None):
    profile = get_profile_data(user_id)
    state = ensure_tecnica_state(user_id)
    if not profile or not state:
        return None

    official_tecnicas = list_available_tecnicas(user_id, "oficial", role_ids)
    created_tecnicas = list_available_tecnicas(user_id, "criado", role_ids)
    accessible_ids = {tecnica["id"] for tecnica in official_tecnicas + created_tecnicas}

    with get_connection() as conn:
        buffed_count = 0
        if accessible_ids:
            placeholders = ",".join("?" for _ in accessible_ids)
            buffed_count = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM tecnicas
                WHERE id IN ({placeholders})
                  AND (COALESCE(multiplicador, 0) > 0 OR COALESCE(bonus_fixo, 0) > 0)
                """,
                tuple(accessible_ids),
            ).fetchone()[0]
        active_row = conn.execute(
            """
            SELECT COUNT(DISTINCT tecnica_uso_id), COALESCE(MAX(turnos_restantes), 0)
            FROM attribute_modifiers
            WHERE user_id = ? AND origem = 'tecnica' AND ativo = 1
            """,
            (user_id,),
        ).fetchone()

    active_buffs = active_row[0] if active_row else 0
    active_turns = active_row[1] if active_row else 0
    last_name = state.get("ultimo_tecnica") or "Nenhuma"
    last_type = "Sem registro" if last_name == "Nenhuma" else "Buff físico"

    return {
        "title": "SISTEMA DE TÉCNICAS",
        "subtitle": "技術システム",
        "name": profile.get("nome"),
        "race": profile.get("raca"),
        "spirit_level": profile.get("nivel"),
        "potential": profile.get("potencial_nome"),
        "reiatsu": profile.get("reiatsu", 0),
        "reiatsu_max": profile.get("reiatsu_max", profile.get("reiatsu_cap", 1)),
        "reiatsu_cap": profile.get("reiatsu_cap", 1),
        "cooldown": state.get("cooldown", 0),
        "uses": state.get("usos_total", 0),
        "official_count": len(official_tecnicas),
        "created_count": len(created_tecnicas),
        "buffed_count": buffed_count,
        "active_buffs": active_buffs,
        "active_turns": active_turns,
        "last_tecnica_name": last_name,
        "last_tecnica_type": last_type,
        "attributes": profile.get("attributes", {}),
    }


async def build_tecnica_image_embed(user_id, member=None):
    data = build_tecnica_card_data(user_id, _member_role_ids(member))
    if not data:
        return None, None

    avatar = await read_discord_avatar(member, size=512)
    # Evita que o CPU-bound do Pillow bloqueie o heartbeat do bot
    buffer = await asyncio.to_thread(create_tecnica_card, data, avatar_source=avatar)
    filename = f"tecnica_card_{user_id}.png"
    file = discord.File(buffer, filename=filename)
    embed = discord.Embed(
        title="Menu de Técnicas",
        description="Escolha uma ação pelos botões abaixo.",
        color=0x2ecc71,
    )
    embed.set_image(url=f"attachment://{filename}")
    return file, embed


def build_list_embed(
    classificacao,
    user_id=None,
    include_private=False,
    page=0,
    per_page=LIST_PER_PAGE,
    available_only=False,
    role_ids=None,
):
    tecnicas = _tecnica_list_rows(classificacao, user_id, include_private, available_only, role_ids)
    total = len(tecnicas)
    max_page = max(0, (total - 1) // per_page)
    page = max(0, min(page, max_page))
    start = page * per_page
    visible = tecnicas[start:start + per_page]

    class_label = normalize_classification(classificacao) or "oficial"
    title = "📚 " + CLASSIFICATION_LABELS.get(class_label, "Técnicas")
    embed = discord.Embed(title=title, color=0x2ecc71)
    if not tecnicas:
        embed.description = "Nenhuma técnica cadastrada nesta classificação."
        embed.set_footer(text="Página 1/1.")
        return embed, tecnicas

    if available_only:
        embed.description = f"`{total}` técnica(s) disponível(is) para este personagem."
    else:
        embed.description = f"`{total}` técnica(s) cadastrada(s) nesta classificação."

    for tecnica in visible:
        dono = f" | Criador: `{tecnica['criador_id']}`" if include_private and tecnica["criador_id"] else ""
        raca = tecnica.get("raca") or "Todas"
        value = "\n".join(
            [
                f"Categoria: `{tecnica['categoria']}`",
                f"Raça: `{raca}`",
                f"Status: `{_tecnica_status_label(tecnica, available_only)}`",
                f"Buff: `{_format_buff(tecnica)}` | Alvo: `{format_targets(tecnica['atributo'])}`{dono}",
            ]
        )
        embed.add_field(
            name=f"ID {tecnica['id']} - {tecnica['nome']}",
            value=value,
            inline=False,
        )
    embed.set_footer(text=f"Mostrando {start + 1}-{start + len(visible)} de {total}. Página {page + 1}/{max_page + 1}.")
    return embed, tecnicas


def build_status_embed(user_id):
    state = ensure_tecnica_state(user_id)
    if not state:
        return None
    embed = discord.Embed(title="⚔️ Sistema de Técnicas", color=0x2ecc71)
    embed.description = "Escolha uma ação pelos botões abaixo."
    embed.add_field(name="Cooldown", value=f"`{state['cooldown']}` turno(s)", inline=True)
    embed.add_field(name="Usos", value=f"`{state['usos_total']}`", inline=True)
    embed.add_field(name="Última técnica", value=f"`{state['ultimo_tecnica'] or 'Nenhuma'}`", inline=False)
    return embed


def build_use_embed(data):
    tecnica = data["tecnica"]
    embed = discord.Embed(title=f"⚔️ {tecnica['nome']}", color=0x2ecc71)
    embed.description = tecnica.get("descricao") or "Sem descrição cadastrada."
    embed.add_field(name="Categoria", value=f"`{tecnica['categoria']}`", inline=True)
    embed.add_field(name="Atributos", value=f"`{format_targets(tecnica['atributo'])}`", inline=True)
    embed.add_field(name="Buff", value=f"`{_format_buff(tecnica)}`", inline=True)
    passive = data.get("pericia_bonus") or 0
    if passive:
        embed.add_field(name="Perícia", value=f"`+{int(float(passive) * 100)}% na técnica`", inline=True)
    if data.get("turn_bonus"):
        embed.add_field(name="Turnos extras", value=f"`+{data['turn_bonus']}`", inline=True)
    embed.add_field(name="Duração", value=f"`{data['duracao']}` turno(s)", inline=True)
    embed.add_field(name="Cooldown", value=f"`{data['cooldown']}` turno(s)", inline=True)
    state = data["state"]
    embed.add_field(name="Estado", value=f"Cooldown atual: `{state['cooldown']}` turno(s)", inline=False)
    return embed


def build_tecnica_use_menu_embed(view):
    embed = discord.Embed(
        title="⚔️ Usar Técnica",
        description="Escolha uma classificação disponível para aplicar uma técnica.",
        color=0x2ecc71,
    )
    if not view.has_categories:
        embed.description = "Você ainda não possui técnicas disponíveis para usar."
    return embed


async def edit_tecnica_status_message(interaction, user_id, from_profile=False, profile_layout="desktop"):
    if not interaction.response.is_done():
        await interaction.response.defer()
    member = _resolve_member(interaction.client, interaction.guild, user_id)
    file, embed = await build_tecnica_image_embed(user_id, member)
    view = TecnicaMenuView(user_id, from_profile, profile_layout)
    if not file:
        embed = build_status_embed(user_id)
        if not embed:
            return await interaction.edit_original_response(
                content="❌ Você não possui um personagem.",
                attachments=[],
                view=None,
            )
        return await interaction.edit_original_response(content=None, embed=embed, attachments=[], view=view)
    await interaction.edit_original_response(content=None, embed=embed, attachments=[file], view=view)


class TecnicaCreateModal(ui.Modal):
    def __init__(self, classificacao, criador_id=None):
        super().__init__(title=CREATE_TYPE_LABELS.get(classificacao, "Criar Técnica"))
        self.classificacao = classificacao
        self.criador_id = criador_id
        self.nome = ui.TextInput(label="Nome da técnica", placeholder="Ex: Shunpo")
        self.categoria = ui.TextInput(label="Categoria", placeholder="Ex: Hakuda, Zanjutsu, Sonído")
        self.descricao = ui.TextInput(
            label="Descrição",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=600,
            placeholder="Explique o efeito da técnica. O buff é configurado depois em .buffar.",
        )
        self.add_item(self.nome)
        self.add_item(self.categoria)
        self.add_item(self.descricao)

    async def on_submit(self, interaction):
        ok, msg, tecnica_id = create_tecnica(
            self.nome.value,
            self.categoria.value,
            self.classificacao,
            self.criador_id,
            self.descricao.value,
        )
        prefix = "✅" if ok else "❌"
        extra = f" ID `{tecnica_id}`." if ok else ""
        await interaction.response.send_message(f"{prefix} {msg}{extra}", ephemeral=True)


class TecnicaCreateTypeSelect(ui.Select):
    def __init__(self, parent):
        options = [discord.SelectOption(label="Criada", value="criado", description="Técnica própria do personagem.")]
        if parent.is_admin:
            options.append(discord.SelectOption(label="Oficial", value="oficial", description="Registro oficial do sistema."))
        super().__init__(placeholder="Escolha o tipo de técnica...", options=options, row=0)
        self.parent_menu = parent

    async def callback(self, interaction):
        if interaction.user.id != self.parent_menu.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        self.parent_menu.classificacao = self.values[0]
        await interaction.response.edit_message(embed=self.parent_menu.build_embed("Tipo selecionado."), view=self.parent_menu)


class TecnicaCreateMenuView(ui.View):
    def __init__(self, user_id, is_admin=False, from_profile=False, profile_layout="desktop", show_back=False):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.is_admin = is_admin
        self.from_profile = from_profile
        self.profile_layout = profile_layout
        self.show_back = show_back
        self.classificacao = "criado"
        self.add_item(TecnicaCreateTypeSelect(self))
        if not show_back:
            for item in list(self.children):
                if getattr(item, "label", None) == "Voltar ao Status":
                    self.remove_item(item)

    def build_embed(self, status=None):
        embed = discord.Embed(title="🖋️ Criação de Técnica", color=0x2ecc71)
        embed.description = "Crie a técnica sem buff. Depois, a staff configura o bônus em `.buffar`."
        embed.add_field(name="Tipo", value=f"`{CREATE_TYPE_LABELS.get(self.classificacao)}`", inline=False)
        if status:
            embed.set_footer(text=status)
        return embed

    @ui.button(label="Abrir formulário", style=discord.ButtonStyle.secondary, row=1)
    async def criar(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        if self.classificacao == "oficial" and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores registram técnicas oficiais.", ephemeral=True)
        criador_id = None if self.classificacao == "oficial" else self.user_id
        await interaction.response.send_modal(TecnicaCreateModal(self.classificacao, criador_id))

    @ui.button(label="Voltar ao Status", style=discord.ButtonStyle.secondary, row=1)
    async def voltar_status(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        await edit_tecnica_status_message(interaction, self.user_id, self.from_profile, self.profile_layout)


class TecnicaSelect(ui.Select):
    PAGE_SIZE = 25

    def __init__(self, parent):
        self.parent_menu = parent
        start = parent.page * self.PAGE_SIZE
        visible = parent.tecnicas[start:start + self.PAGE_SIZE]
        options = [
            discord.SelectOption(
                label=f"{tecnica['nome']} ({tecnica['categoria']})"[:100],
                value=str(tecnica["id"]),
                description=f"Buff: {_format_buff(tecnica)} | {format_targets(tecnica['atributo'])}"[:100],
            )
            for tecnica in visible
        ]
        super().__init__(placeholder="Escolha a técnica...", options=options, min_values=1, max_values=1, row=0)

    async def callback(self, interaction):
        if interaction.user.id != self.parent_menu.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        self.parent_menu.selected_id = int(self.values[0])
        self.parent_menu.refresh_items()
        await interaction.response.edit_message(embed=self.parent_menu.build_embed("Técnica selecionada."), view=self.parent_menu)


class TecnicaStatusReturnView(ui.View):
    def __init__(self, user_id, from_profile=False, profile_layout="desktop"):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.from_profile = from_profile
        self.profile_layout = profile_layout

    @ui.button(label="Voltar ao Status", style=discord.ButtonStyle.secondary)
    async def voltar_status(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        await edit_tecnica_status_message(interaction, self.user_id, self.from_profile, self.profile_layout)


class TecnicaUseListView(ui.View):
    PAGE_SIZE = 25

    def __init__(self, user_id, classificacao, tecnicas, role_ids=None, from_profile=False, profile_layout="desktop"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.classificacao = classificacao
        self.tecnicas = tecnicas
        self.role_ids = role_ids or []
        self.from_profile = from_profile
        self.profile_layout = profile_layout
        self.page = 0
        self.selected_id = None
        self.refresh_items()

    @property
    def max_page(self):
        return max(0, (len(self.tecnicas) - 1) // self.PAGE_SIZE)

    def selected_tecnica(self):
        for tecnica in self.tecnicas:
            if tecnica["id"] == self.selected_id:
                return tecnica
        return None

    def build_embed(self, status=None):
        embed = discord.Embed(title="⚔️ " + CLASSIFICATION_LABELS.get(self.classificacao, "Técnicas"), color=0x2ecc71)
        embed.description = "Selecione uma técnica e use para aplicar o buff físico configurado."
        embed.add_field(name="Disponíveis", value=f"`{len(self.tecnicas)}`", inline=True)
        embed.add_field(name="Página", value=f"`{self.page + 1}/{self.max_page + 1}`", inline=True)
        selected = self.selected_tecnica()
        embed.add_field(name="Seleção", value=f"`{selected['nome']}`" if selected else "`Nenhuma`", inline=False)
        if status:
            embed.set_footer(text=status)
        return embed

    def refresh_items(self):
        self.clear_items()
        if self.tecnicas:
            self.add_item(TecnicaSelect(self))

        usar = ui.Button(label="Usar Técnica", style=discord.ButtonStyle.success, row=1, disabled=self.selected_id is None)
        usar.callback = self.usar
        self.add_item(usar)

        if self.max_page > 0:
            prev_page = ui.Button(label="⬅️", style=discord.ButtonStyle.secondary, row=2, disabled=self.page <= 0)
            prev_page.callback = self.prev_page
            next_page = ui.Button(label="➡️", style=discord.ButtonStyle.secondary, row=2, disabled=self.page >= self.max_page)
            next_page.callback = self.next_page
            self.add_item(prev_page)
            self.add_item(next_page)

        voltar_status = ui.Button(label="Voltar ao Status", style=discord.ButtonStyle.secondary, row=3)
        voltar_status.callback = self.voltar_status
        self.add_item(voltar_status)

    async def _guard(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
            return False
        return True

    async def usar(self, interaction):
        if not await self._guard(interaction):
            return
        if self.selected_id is None:
            return await interaction.response.edit_message(embed=self.build_embed("❌ Selecione uma técnica."), view=self)
        role_ids = _member_role_ids(interaction.user) or self.role_ids
        ok, msg, data = use_tecnica(self.user_id, self.selected_id, role_ids)
        if not ok:
            return await interaction.response.edit_message(embed=self.build_embed(f"❌ {msg}"), view=self)
        await interaction.response.edit_message(
            embed=build_use_embed(data),
            view=TecnicaStatusReturnView(self.user_id, self.from_profile, self.profile_layout),
        )

    async def voltar_status(self, interaction):
        if not await self._guard(interaction):
            return
        await edit_tecnica_status_message(interaction, self.user_id, self.from_profile, self.profile_layout)

    async def prev_page(self, interaction):
        if not await self._guard(interaction):
            return
        self.page = max(0, self.page - 1)
        self.selected_id = None
        self.refresh_items()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def next_page(self, interaction):
        if not await self._guard(interaction):
            return
        self.page = min(self.max_page, self.page + 1)
        self.selected_id = None
        self.refresh_items()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class TecnicaUseMenuView(ui.View):
    def __init__(self, user_id, role_ids=None, from_profile=False, profile_layout="desktop"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.role_ids = role_ids or []
        self.from_profile = from_profile
        self.profile_layout = profile_layout
        self.known_by_class = {
            classificacao: list_available_tecnicas(user_id, classificacao, self.role_ids)
            for classificacao in ("oficial", "criado")
        }
        self._add_class_button("oficial")
        self._add_class_button("criado")
        voltar_status = ui.Button(label="Voltar ao Status", style=discord.ButtonStyle.secondary, row=1)
        voltar_status.callback = self.voltar_status
        self.add_item(voltar_status)

    @property
    def has_categories(self):
        return any(self.known_by_class.values())

    def _add_class_button(self, classificacao):
        if not self.known_by_class.get(classificacao):
            return
        button = ui.Button(label=CLASSIFICATION_LABELS[classificacao], style=discord.ButtonStyle.secondary)
        button.callback = self._make_category_callback(classificacao)
        self.add_item(button)

    def _make_category_callback(self, classificacao):
        async def callback(interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
            role_ids = _member_role_ids(interaction.user) or self.role_ids
            tecnicas = list_available_tecnicas(self.user_id, classificacao, role_ids)
            if not tecnicas:
                return await interaction.response.edit_message(
                    embed=discord.Embed(title="⚔️ Usar Técnica", description="❌ Nenhuma técnica disponível.", color=0x2ecc71),
                    view=self,
                )
            view = TecnicaUseListView(
                self.user_id,
                classificacao,
                tecnicas,
                role_ids,
                self.from_profile,
                self.profile_layout,
            )
            await interaction.response.edit_message(embed=view.build_embed(), view=view)
        return callback

    async def voltar_status(self, interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        await edit_tecnica_status_message(interaction, self.user_id, self.from_profile, self.profile_layout)


class TecnicaMenuView(ui.View):
    def __init__(self, user_id, from_profile=False, profile_layout="desktop"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.from_profile = from_profile
        self.profile_layout = profile_layout
        if not from_profile:
            for item in list(self.children):
                if getattr(item, "label", None) == "Perfil":
                    self.remove_item(item)

    async def _guard(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
            return False
        return True

    @ui.button(label="Status", style=discord.ButtonStyle.success, row=1)
    async def status(self, interaction, button):
        if not await self._guard(interaction):
            return
        await edit_tecnica_status_message(interaction, self.user_id, self.from_profile, self.profile_layout)

    @ui.button(label="Usar", style=discord.ButtonStyle.success, row=1)
    async def usar_tecnica(self, interaction, button):
        if not await self._guard(interaction):
            return
        role_ids = _member_role_ids(interaction.user)
        view = TecnicaUseMenuView(self.user_id, role_ids, self.from_profile, self.profile_layout)
        await interaction.response.edit_message(
            embed=build_tecnica_use_menu_embed(view),
            attachments=[],
            view=view,
        )

    @ui.button(label="Criar Técnica", style=discord.ButtonStyle.secondary, row=1)
    async def criar_tecnica(self, interaction, button):
        if not await self._guard(interaction):
            return
        view = TecnicaCreateMenuView(
            self.user_id,
            interaction.user.guild_permissions.administrator,
            self.from_profile,
            self.profile_layout,
            show_back=True,
        )
        await interaction.response.edit_message(
            embed=view.build_embed(),
            attachments=[],
            view=view,
        )

    @ui.button(label="Técnicas Oficiais", style=discord.ButtonStyle.secondary, row=0)
    async def oficiais(self, interaction, button):
        if not await self._guard(interaction):
            return
        role_ids = _member_role_ids(interaction.user)
        view = TecnicaListView(
            "oficial",
            user_id=self.user_id,
            available_only=True,
            role_ids=role_ids,
            allow_switch=False,
            viewer_id=self.user_id,
        )
        embed, _ = build_list_embed(
            "oficial",
            user_id=self.user_id,
            available_only=True,
            role_ids=role_ids,
            per_page=view.per_page,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ui.button(label="Técnicas Criadas", style=discord.ButtonStyle.secondary, row=0)
    async def criadas(self, interaction, button):
        if not await self._guard(interaction):
            return
        view = TecnicaListView(
            "criado",
            user_id=self.user_id,
            available_only=True,
            role_ids=_member_role_ids(interaction.user),
            allow_switch=False,
            viewer_id=self.user_id,
        )
        embed, _ = build_list_embed(
            "criado",
            user_id=self.user_id,
            available_only=True,
            per_page=view.per_page,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ui.button(label="Perfil", style=discord.ButtonStyle.secondary, row=1)
    async def perfil(self, interaction, button):
        if not await self._guard(interaction):
            return
        from cogs.player_system import PerfilView, build_profile_image_embed

        member = _resolve_member(interaction.client, interaction.guild, self.user_id)
        file, embed = await build_profile_image_embed(self.user_id, member, self.profile_layout)
        if not file:
            return await interaction.response.send_message("❌ Personagem não encontrado.", ephemeral=True)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=PerfilView(self.user_id, self.profile_layout))


class TecnicaListView(ui.View):
    def __init__(
        self,
        classificacao="oficial",
        page=0,
        user_id=None,
        include_private=True,
        available_only=False,
        role_ids=None,
        allow_switch=True,
        viewer_id=None,
        per_page=LIST_PER_PAGE,
    ):
        super().__init__(timeout=120)
        self.classificacao = classificacao
        self.page = page
        self.user_id = user_id
        self.include_private = include_private
        self.available_only = available_only
        self.role_ids = role_ids or []
        self.allow_switch = allow_switch
        self.viewer_id = viewer_id
        self.per_page = per_page
        if not allow_switch:
            for item in list(self.children):
                if getattr(item, "label", None) in ("Oficiais", "Criadas"):
                    self.remove_item(item)
        self._sync_nav_buttons()

    def _sync_nav_buttons(self):
        total = len(
            _tecnica_list_rows(
                self.classificacao,
                self.user_id,
                self.include_private,
                self.available_only,
                self.role_ids,
            )
        )
        max_page = max(0, (total - 1) // self.per_page)
        self.page = max(0, min(self.page, max_page))
        self.prev_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= max_page

    async def _show(self, interaction, classificacao=None, page=None):
        if self.viewer_id and interaction.user.id != self.viewer_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        if classificacao is not None:
            self.classificacao = classificacao
            self.page = 0
        if page is not None:
            self.page = page
        self._sync_nav_buttons()
        embed, _ = build_list_embed(
            self.classificacao,
            user_id=self.user_id,
            include_private=self.include_private,
            page=self.page,
            per_page=self.per_page,
            available_only=self.available_only,
            role_ids=self.role_ids,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Oficiais", style=discord.ButtonStyle.primary)
    async def oficiais(self, interaction, button):
        await self._show(interaction, "oficial")

    @ui.button(label="Criadas", style=discord.ButtonStyle.primary)
    async def criadas(self, interaction, button):
        await self._show(interaction, "criado")

    @ui.button(label="Anterior", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction, button):
        await self._show(interaction, page=self.page - 1)

    @ui.button(label="Próxima", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction, button):
        await self._show(interaction, page=self.page + 1)


class TecnicaSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="tecnica", aliases=["técnica", "tecnicas", "técnicas"], invoke_without_command=True)
    async def tecnica(self, ctx):
        file, embed = await build_tecnica_image_embed(ctx.author.id, ctx.author)
        if not embed:
            return await ctx.send("❌ Você não possui um personagem.")
        await ctx.send(file=file, embed=embed, view=TecnicaMenuView(ctx.author.id))

    @commands.command(name="tecnica_criar", aliases=["técnica_criar", "tecnicas_criar", "técnicas_criar"])
    async def tecnica_criar(self, ctx):
        if not ensure_tecnica_state(ctx.author.id):
            return await ctx.send("❌ Você não possui um personagem.")
        view = TecnicaCreateMenuView(ctx.author.id, ctx.author.guild_permissions.administrator)
        await ctx.send(embed=view.build_embed(), view=view)

    @commands.command(name="listar_tecnicas", aliases=["listar_técnicas", "listar_tecnica", "listar_técnica"])
    async def listar_tecnicas_cmd(self, ctx):
        embed = discord.Embed(
            title="📚 Lista de Técnicas",
            description="Escolha a classificação que deseja consultar.",
            color=0x2ecc71,
        )
        await ctx.send(embed=embed, view=TecnicaListView())

    @tecnica.command(name="criar")
    async def criar(self, ctx):
        await self.tecnica_criar(ctx)

    @commands.command(name="setar_buff_tecnica", hidden=True)
    @commands.has_permissions(administrator=True)
    async def setar_buff_tecnica(self, ctx, tecnica_id: int, multiplicador: str, bonus_fixo: str, atributo: str = "todos", duracao: int = 1, cooldown: int = 1):
        ok, msg, _ = configure_tecnica_buff(tecnica_id, multiplicador, bonus_fixo, atributo, duracao, cooldown)
        await ctx.send(("✅ " if ok else "❌ ") + msg)

    @commands.command(name="setar_tecnica", aliases=["setar_técnica", "liberar_tecnica", "liberar_técnica"])
    @commands.has_permissions(administrator=True)
    async def setar_tecnica(self, ctx, *, entrada: str):
        target_type, target, nome, error = _extract_unlock_args(ctx, entrada)
        if error:
            return await ctx.send("❌ " + error)

        if target_type == "role":
            ok, msg, tecnica_id = grant_tecnica_to_role(nome, target.id)
            target_label = target.name
        else:
            ok, msg, tecnica_id = grant_tecnica_to_user(nome, target.id)
            target_label = target.display_name
        if not ok:
            return await ctx.send("❌ " + msg)
        await ctx.send(f"✅ {msg} `{target_label}`. ID `{tecnica_id}`.")


async def setup(bot):
    await bot.add_cog(TecnicaSystem(bot))
