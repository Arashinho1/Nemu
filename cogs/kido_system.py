import discord
import asyncio
from discord import ui
from discord.ext import commands

from utils.kido_service import (
    calculate_kido,
    create_kido_tecnica,
    ensure_kido_state,
    get_last_kido_power,
    grant_kido_tecnica,
    has_kido_access,
    list_known_kido_tecnicas,
    list_kido_tecnicas,
    parse_percent,
    use_kaido_heal,
    use_niju_eisho,
    use_kido_tecnica,
)
from utils.avatar import read_discord_avatar
from utils.kido_template import create_kido_card
from utils.profile_service import get_profile_data
from database import get_connection


KIDO_CLASSIFICATION_LABELS = {
    "oficial": "Kidō Oficiais",
    "criado": "Kidō Criados",
    "exclusivo": "Kidō Exclusivos",
    "proibido": "Kidō Proibidos",
}

KIDO_CREATE_TYPE_LABELS = {
    "criado": "Comum",
    "exclusivo": "Exclusivo",
    "proibido": "Proibido",
    "oficial": "Oficial",
    "exclusivo_global": "Exclusivo do Sistema",
    "proibido_global": "Proibido do Sistema",
}

KIDO_TECHNICAL_CATEGORY_LABELS = {
    "hado": "Hadō",
    "bakudo": "Bakudō",
    "kaido": "Kaidō",
}
KIDO_ACCESS_ERROR = "❌ Apenas personagens Shinigami ou Vaizard podem acessar Kidō."


def _resolve_member(client, guild, user_id):
    if guild:
        member = guild.get_member(int(user_id))
        if member:
            return member
    return client.get_user(int(user_id)) if client else None


def _split_last_kido(value):
    text = (value or "").strip()
    if not text:
        return "Nenhum", "Sem registro"
    if "(" in text and text.endswith(")"):
        name, kind = text.rsplit("(", 1)
        return name.strip() or "Nenhum", kind[:-1].strip() or "Sem registro"
    return text, "Sem registro"


def _format_tecnica_label(tecnica):
    return f"{tecnica['categoria']} #{tecnica['numero']} - {tecnica['nome']}"


def _format_method_adjustment(data):
    multiplier = data.get("power_multiplier", 1.0)
    percent = int(round((multiplier - 1.0) * 100))
    if percent > 0:
        return f"+{percent}% em potência e consumo"
    if percent < 0:
        return f"{percent}% em potência e consumo"
    return "sem ajuste"


def _format_kido_potential_label(user_id, fallback):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT potencial
            FROM player_potencial
            WHERE user_id = ? AND ativo = 1
            ORDER BY potencial COLLATE NOCASE
            """,
            (user_id,),
        ).fetchall()

    names = [row[0] for row in rows if row and row[0]]
    if not names:
        return fallback or "Nenhum"
    if len(names) <= 2:
        return " + ".join(names)
    return f"{len(names)} POTENCIAIS ATIVOS"


def build_kido_card_data(user_id):
    if not has_kido_access(user_id):
        return None

    profile = get_profile_data(user_id)
    state = ensure_kido_state(user_id)
    if not profile or not state:
        return None

    preview = calculate_kido(user_id, 1)
    last_name, last_type = _split_last_kido(state.get("ultimo_kido"))
    last_power = state.get("ultimo_poder") or get_last_kido_power(user_id)
    return {
        "title": "SISTEMA DE KIDŌ",
        "subtitle": "鬼道システム",
        "name": profile.get("nome"),
        "race": profile.get("raca"),
        "spirit_level": profile.get("nivel"),
        "potential": _format_kido_potential_label(user_id, profile.get("potencial_nome")),
        "reiatsu": profile.get("reiatsu", 0),
        "reiatsu_max": profile.get("reiatsu_max", profile.get("reiatsu_cap", 1)),
        "reiatsu_cap": profile.get("reiatsu_cap", 1),
        "reiryoku": state.get("reiryoku_atual", 0),
        "reiryoku_max": state.get("reiryoku_max", 1),
        "cooldown": state.get("cooldown", 0),
        "tier": f"{preview['tier']} / 6",
        "access": f"#1 ao #{preview['max_number']}",
        "skill_bonus": f"+{int(preview['pericia_bonus'] * 100)}%",
        "uses": state.get("usos_total", 0),
        "total_cost": state.get("gasto_total", 0),
        "power_total": state.get("poder_total", 0),
        "last_power": last_power,
        "last_kido_name": last_name,
        "last_kido_type": last_type,
    }


async def build_kido_image_embed(user_id, member=None):
    data = build_kido_card_data(user_id)
    if not data:
        return None, None

    avatar = await read_discord_avatar(member, size=512)
    # Renderização em thread separada para manter a responsividade
    buffer = await asyncio.to_thread(create_kido_card, data, avatar_source=avatar)
    filename = f"kido_card_{user_id}.png"
    file = discord.File(buffer, filename=filename)
    embed = discord.Embed(
        title="Menu de Kidō",
        description="Escolha uma ação pelos botões abaixo.",
        color=discord.Color.purple(),
    )
    embed.set_image(url=f"attachment://{filename}")
    return file, embed


def build_status_embed(user_id):
    if not has_kido_access(user_id):
        return None

    state = ensure_kido_state(user_id)
    if not state:
        return None

    preview = calculate_kido(user_id, 1)
    embed = discord.Embed(title="🔮 Menu de Kidō", color=0x7f8cff)
    embed.description = "Escolha uma ação pelos botões abaixo."
    embed.add_field(
        name="Energia",
        value=f"Reiryoku: `{state['reiryoku_atual']}/{state['reiryoku_max']}`\nCooldown: `{state['cooldown']} turno(s)`",
        inline=False,
    )
    embed.add_field(
        name="Domínio",
        value=(
            f"Tier: `{preview['tier']}/6`\n"
            f"Acesso: `#1 ao #{preview['max_number']}`\n"
            f"Bônus de perícia: `+{int(preview['pericia_bonus'] * 100)}%`"
        ),
        inline=True,
    )
    last_power = state.get("ultimo_poder") or get_last_kido_power(user_id)
    embed.add_field(
        name="Uso contabilizado",
        value=(
            f"Usos: `{state['usos_total']}`\n"
            f"Gasto total: `{state['gasto_total']}`\n"
            f"Última potência: `{last_power}`\n"
            f"Potência total: `{state['poder_total']}`"
        ),
        inline=True,
    )
    if state["ultimo_kido"]:
        embed.set_footer(text=f"Último Kidō: {state['ultimo_kido']}")
    return embed


def build_list_embed(classificacao, user_id=None, include_private=False, known_only=False, page=0, per_page=10):
    tecnicas = list_kido_tecnicas(classificacao, user_id, include_private)
    if known_only and user_id and classificacao == "oficial":
        max_number = calculate_kido(user_id, 1)["max_number"]
        tecnicas = [t for t in tecnicas if t["numero"] <= max_number]
    total = len(tecnicas)
    max_page = max(0, (total - 1) // per_page)
    page = max(0, min(page, max_page))
    start = page * per_page
    visible = tecnicas[start:start + per_page]

    titles = {
        "oficial": "📜 Kidō Oficiais",
        "criado": "📜 Kidō Criados",
        "exclusivo": "🌟 Kidō Exclusivos",
        "proibido": "⛔ Kidō Proibidos",
    }
    title = titles.get(classificacao, "📜 Kidō")
    embed = discord.Embed(title=title, color=0x95a5ff)
    if not tecnicas:
        embed.description = "Nenhum Kidō cadastrado nesta classificação."
        return embed, tecnicas

    lines = []
    for tecnica in visible:
        dono = f" | Criador: `{tecnica['criador_id']}`" if tecnica["classificacao"] == "criado" and include_private else ""
        lines.append(f"`ID {tecnica['id']}` • **{tecnica['categoria']} #{tecnica['numero']}** — {tecnica['nome']}{dono}")
    embed.description = "\n".join(lines)
    if classificacao == "exclusivo":
        embed.add_field(name="Acesso", value="Kidō exclusivos são liberados por premiação, vaga ou autorização da staff.", inline=False)
    if classificacao == "proibido":
        embed.add_field(name="Acesso", value="Kidō proibidos não são liberados por evolução comum de perícia.", inline=False)
    if total > per_page:
        embed.set_footer(text=f"Mostrando {start + 1}-{start + len(visible)} de {total} Kidō cadastrados. Página {page + 1}/{max_page + 1}.")
    return embed, tecnicas


def build_use_embed(data):
    state = data["state"]
    if data.get("action") == "heal":
        title = "🔮 Kaidō: Curar"
        embed = discord.Embed(title=title, color=0x7f8cff)
        embed.add_field(name="Ação", value="`Curar`", inline=True)
        embed.add_field(name="Tier", value=f"`{data['tier']}/6`", inline=True)
        embed.add_field(name="Custo", value=f"`{data['cost']}` Reiryoku", inline=True)
        embed.add_field(name="Reiryoku restaurado", value=f"`{data['restored']}/{data['heal']}`", inline=True)
        embed.add_field(name="Escala", value=f"`{int(data['restore_percent'] * 100)}%` do Reiryoku máximo", inline=True)
        embed.add_field(name="Reiatsu efetiva", value=f"`{data['reiatsu']}`", inline=True)
        embed.add_field(name="Cooldown", value=f"`{data['cooldown']}` turno(s)", inline=True)
        embed.add_field(
            name="Estado",
            value=f"Reiryoku: `{state['reiryoku_atual']}/{state['reiryoku_max']}`\nCooldown: `{state['cooldown']} turno(s)`",
            inline=False,
        )
        return embed

    if data.get("techniques"):
        embed = discord.Embed(title="🔮 Nijū Eishō", color=0x7f8cff)
        embed.add_field(name="Método", value=f"`{data['method']}`", inline=True)
        embed.add_field(name="Gasto total", value=f"`{data['cost']}` Reiryoku", inline=True)
        embed.add_field(name="Potência total", value=f"`{data['damage']}`", inline=True)
        for item in data["techniques"]:
            tecnica = item["tecnica"]
            embed.add_field(
                name=f"{tecnica['nome']} ({item['category']} #{item['number']})",
                value=(
                    f"Gasto: `{item['cost']}` | Potência: `{item['damage']}` | "
                    f"Cooldown: `{item['cooldown']}` turno(s)"
                ),
                inline=False,
            )
        embed.add_field(
            name="Estado",
            value=f"Reiryoku: `{state['reiryoku_atual']}/{state['reiryoku_max']}`\nCooldown: `{state['cooldown']} turno(s)`",
            inline=False,
        )
        return embed

    title = f"🔮 {data['category']} #{data['number']}"
    if data.get("tecnica"):
        title = f"🔮 {data['tecnica']['nome']}"
    embed = discord.Embed(title=title, color=0x7f8cff)
    embed.add_field(name="Método", value=f"`{data['method']}`", inline=True)
    embed.add_field(name="Gasto", value=f"`{data['cost']}` Reiryoku", inline=True)
    embed.add_field(name="Reiatsu efetiva", value=f"`{data['reiatsu']}`", inline=True)
    embed.add_field(name="Ajuste do método", value=f"`{_format_method_adjustment(data)}`", inline=True)
    embed.add_field(name="Bônus da técnica", value=f"`+{int(data['technique_bonus'] * 100)}%`", inline=True)
    embed.add_field(name="Bônus total", value=f"`+{int(data['total_bonus'] * 100)}%`", inline=True)
    embed.add_field(name="Potência Kidō", value=f"`{data['damage']}`", inline=True)
    embed.add_field(
        name="Estado",
        value=f"Reiryoku: `{state['reiryoku_atual']}/{state['reiryoku_max']}`\nCooldown: `{state['cooldown']} turno(s)`",
        inline=False,
    )
    return embed


def build_kido_use_menu_embed(view):
    embed = discord.Embed(
        title="🔮 Usar Kidō",
        description="Escolha uma classificação disponível ou abra Kaidō para ações de cura.",
        color=0x7f8cff,
    )
    if not view.has_categories:
        embed.description = "Você ainda não possui Kidō disponível para conjurar."
    return embed


async def edit_kido_status_message(interaction, user_id, from_profile=False, profile_layout="desktop"):
    if not interaction.response.is_done():
        await interaction.response.defer()
    member = _resolve_member(interaction.client, interaction.guild, user_id)
    file, embed = await build_kido_image_embed(user_id, member)
    view = KidoMenuView(user_id, interaction.client, from_profile, profile_layout)
    if not file:
        embed = build_status_embed(user_id)
        if not embed:
            return await interaction.edit_original_response(
                content=KIDO_ACCESS_ERROR,
                attachments=[],
                view=None,
            )
        return await interaction.edit_original_response(content=None, embed=embed, attachments=[], view=view)
    await interaction.edit_original_response(content=None, embed=embed, attachments=[file], view=view)


class KidoCreateModal(ui.Modal):
    def __init__(self, classificacao, categoria, criador_id=None):
        titles = {
            "oficial": "Registrar Kidō Oficial",
            "criado": "Criar Kidō Comum",
            "exclusivo": "Criar Kidō Exclusivo",
            "proibido": "Criar Kidō Proibido",
        }
        title = titles.get(classificacao, "Criar Kidō")
        super().__init__(title=title)
        self.classificacao = classificacao
        self.categoria = categoria
        self.criador_id = criador_id
        self.nome = ui.TextInput(label="Nome do Kidō", placeholder="Ex: Shakkahō")
        self.numero = ui.TextInput(label="Número", placeholder="Ex: 31")
        self.dano_bonus = ui.TextInput(label="Bônus de potência (%)", placeholder="Opcional. Ex: 50 para +50%", required=False)
        self.descricao = ui.TextInput(
            label="Descrição",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=600,
            placeholder="Explique o efeito do Kidō em até 600 caracteres.",
        )
        self.add_item(self.nome)
        self.add_item(self.numero)
        self.add_item(self.dano_bonus)
        self.add_item(self.descricao)

    async def on_submit(self, interaction):
        try:
            numero = int(self.numero.value)
        except ValueError:
            return await interaction.response.send_message("❌ Número inválido.", ephemeral=True)

        ok, msg, tecnica_id = create_kido_tecnica(
            self.nome.value,
            self.categoria,
            numero,
            self.classificacao,
            self.criador_id,
            self.descricao.value,
            self.dano_bonus.value,
        )
        prefix = "✅" if ok else "❌"
        extra = f" ID `{tecnica_id}`." if ok else ""
        await interaction.response.send_message(f"{prefix} {msg}{extra}", ephemeral=True)


class KidoTechniqueSelect(ui.Select):
    PAGE_SIZE = 25

    def __init__(self, parent_menu):
        self.parent_menu = parent_menu
        start = parent_menu.page * self.PAGE_SIZE
        visible = parent_menu.tecnicas[start:start + self.PAGE_SIZE]
        options = [
            discord.SelectOption(
                label=_format_tecnica_label(t)[:100],
                value=str(t["id"]),
                description=(t["descricao"] or "Sem descrição")[:100],
            )
            for t in visible
        ]
        max_values = 2 if parent_menu.allow_niju and len(parent_menu.tecnicas) >= 2 else 1
        max_values = min(max_values, len(options))
        placeholder = "Escolha 1 Kidō, ou 2 para Nijū Eishō..." if max_values == 2 else "Escolha o Kidō..."
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=max_values, row=0)

    async def callback(self, interaction):
        if interaction.user.id != self.parent_menu.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)

        selected = [int(value) for value in self.values]
        if self.parent_menu.allow_niju:
            page_ids = {tecnica["id"] for tecnica in self.parent_menu.current_page_tecnicas()}
            preserved = [tecnica_id for tecnica_id in self.parent_menu.selected_ids if tecnica_id not in page_ids]
            self.parent_menu.selected_ids = (preserved + selected)[-2:]
        else:
            self.parent_menu.selected_ids = selected[:1]

        status = self.parent_menu.format_selection_status()
        self.parent_menu.refresh_items()
        await interaction.response.edit_message(embed=self.parent_menu.build_embed(status), view=self.parent_menu)


class KidoCategorySelect(ui.Select):
    def __init__(self, parent):
        options = [
            discord.SelectOption(label="Hadō", value="hado", description="Técnicas destrutivas e ofensivas."),
            discord.SelectOption(label="Bakudō", value="bakudo", description="Contenção, suporte, barreiras e selos."),
            discord.SelectOption(label="Kaidō", value="kaido", description="Cura e restauração espiritual."),
        ]
        super().__init__(placeholder="Escolha a categoria do Kidō...", options=options)
        self.parent_menu = parent

    async def callback(self, interaction):
        if interaction.user.id != self.parent_menu.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        self.parent_menu.categoria = self.values[0]
        label = KIDO_TECHNICAL_CATEGORY_LABELS[self.values[0]]
        await interaction.response.edit_message(embed=self.parent_menu.build_embed(f"Categoria selecionada: {label}"), view=self.parent_menu)


class KidoCreateTypeSelect(ui.Select):
    def __init__(self, parent):
        options = [
            discord.SelectOption(label="Comum", value="criado", description="Kidō criado pelo seu personagem."),
            discord.SelectOption(label="Exclusivo", value="exclusivo", description="Kidō especial criado pelo seu personagem."),
            discord.SelectOption(label="Proibido", value="proibido", description="Kidō proibido criado pelo seu personagem."),
        ]
        if parent.is_admin:
            options.append(discord.SelectOption(label="Oficial", value="oficial", description="Registro oficial do sistema."))
            options.append(discord.SelectOption(label="Exclusivo Sistema", value="exclusivo_global", description="Registro exclusivo global da staff."))
            options.append(discord.SelectOption(label="Proibido Sistema", value="proibido_global", description="Registro proibido global da staff."))
        super().__init__(placeholder="Escolha a classificação do Kidō...", options=options)
        self.parent_menu = parent

    async def callback(self, interaction):
        if interaction.user.id != self.parent_menu.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        self.parent_menu.classificacao = self.values[0]
        label = KIDO_CREATE_TYPE_LABELS.get(self.values[0], self.values[0])
        await interaction.response.edit_message(embed=self.parent_menu.build_embed(f"Classificação selecionada: {label}"), view=self.parent_menu)


class KidoCreateMenuView(ui.View):
    def __init__(self, user_id, is_admin=False):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.is_admin = is_admin
        self.categoria = None
        self.classificacao = "criado"
        self.add_item(KidoCategorySelect(self))
        self.add_item(KidoCreateTypeSelect(self))

    def build_embed(self, status=None):
        embed = discord.Embed(title="🖋️ Criação de Kidō", color=0x7f8cff)
        embed.description = "Selecione a categoria técnica e a classificação do Kidō."
        category_label = KIDO_TECHNICAL_CATEGORY_LABELS.get(self.categoria, self.categoria or "não selecionada")
        embed.add_field(name="Categoria", value=f"`{category_label}`", inline=False)
        embed.add_field(
            name="Classificação",
            value=f"`{KIDO_CREATE_TYPE_LABELS.get(self.classificacao, self.classificacao)}`",
            inline=False,
        )
        if status:
            embed.set_footer(text=status)
        return embed

    async def _open_modal(self, interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        if not self.categoria:
            return await interaction.response.send_message("❌ Selecione uma categoria antes de continuar.", ephemeral=True)
        global_record = self.classificacao in ("oficial", "exclusivo_global", "proibido_global")
        if global_record and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem registrar Kidō do sistema.", ephemeral=True)
        classificacao = self.classificacao.replace("_global", "")
        criador_id = None if global_record else self.user_id
        await interaction.response.send_modal(KidoCreateModal(classificacao, self.categoria, criador_id))

    @ui.button(label="Abrir formulário", style=discord.ButtonStyle.secondary)
    async def criar(self, interaction, button):
        await self._open_modal(interaction)


class KidoStatusReturnView(ui.View):
    def __init__(self, user_id, from_profile=False, profile_layout="desktop"):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.from_profile = from_profile
        self.profile_layout = profile_layout

    @ui.button(label="Voltar ao Status", style=discord.ButtonStyle.secondary)
    async def voltar_status(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        await edit_kido_status_message(interaction, self.user_id, self.from_profile, self.profile_layout)


class KidoKaidoActionView(ui.View):
    def __init__(self, user_id, from_profile=False, profile_layout="desktop"):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.from_profile = from_profile
        self.profile_layout = profile_layout

    def build_embed(self, status=None):
        embed = discord.Embed(title="🔮 Kaidō", color=0x7f8cff)
        embed.description = "Escolha a ação de Kaidō."
        embed.add_field(name="Tier I-II", value="Cura: `5%`, mínimo `100`\nCusto: `cura x1.50`", inline=True)
        embed.add_field(name="Tier III-IV", value="Cura: `10%`, mínimo `300`\nCusto: `cura x1.35`", inline=True)
        embed.add_field(name="Tier V-VI", value="Cura: `15%`, mínimo `600`\nCusto: `cura x1.25`", inline=True)
        embed.set_footer(text=status or "Kaidō não usa encantamento, número ou nome de técnica.")
        return embed

    @ui.button(label="Curar", style=discord.ButtonStyle.secondary)
    async def curar(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        ok, msg, data = use_kaido_heal(self.user_id)
        if not ok:
            return await interaction.response.edit_message(embed=self.build_embed(f"❌ {msg}"), view=self)
        await interaction.response.edit_message(
            embed=build_use_embed(data),
            view=KidoStatusReturnView(self.user_id, self.from_profile, self.profile_layout),
        )

    @ui.button(label="Voltar ao Status", style=discord.ButtonStyle.secondary, row=1)
    async def voltar_status(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        await edit_kido_status_message(interaction, self.user_id, self.from_profile, self.profile_layout)


class KidoUseListView(ui.View):
    PAGE_SIZE = 25

    def __init__(self, user_id, classificacao, tecnicas, from_profile=False, profile_layout="desktop"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.classificacao = classificacao
        self.tecnicas = tecnicas
        self.from_profile = from_profile
        self.profile_layout = profile_layout
        self.page = 0
        self.selected_ids = []
        self.allow_niju = calculate_kido(user_id, 1)["tier"] >= 3
        self.refresh_items()

    @property
    def max_page(self):
        return max(0, (len(self.tecnicas) - 1) // self.PAGE_SIZE)

    def current_page_tecnicas(self):
        start = self.page * self.PAGE_SIZE
        return self.tecnicas[start:start + self.PAGE_SIZE]

    def selected_tecnicas(self):
        by_id = {tecnica["id"]: tecnica for tecnica in self.tecnicas}
        return [by_id[tecnica_id] for tecnica_id in self.selected_ids if tecnica_id in by_id]

    def format_selection_status(self):
        selected = self.selected_tecnicas()
        if not selected:
            return "Nenhum Kidō selecionado."
        return "Selecionado: " + " + ".join(_format_tecnica_label(tecnica) for tecnica in selected)

    def build_embed(self, status=None):
        title = KIDO_CLASSIFICATION_LABELS.get(self.classificacao, "Kidō")
        embed = discord.Embed(title=f"🔮 {title}", color=0x7f8cff)
        embed.description = "Selecione o Kidō na lista suspensa e escolha o método de conjuração."
        if self.tecnicas:
            embed.add_field(name="Disponíveis", value=f"`{len(self.tecnicas)}` Kidō", inline=True)
            embed.add_field(name="Página", value=f"`{self.page + 1}/{self.max_page + 1}`", inline=True)
        else:
            embed.description = "Nenhum Kidō disponível nesta classificação."
        embed.add_field(name="Seleção", value=status or self.format_selection_status(), inline=False)
        if self.allow_niju and len(self.tecnicas) >= 2:
            embed.set_footer(text="Nijū Eishō exige exatamente 2 Kidō selecionados e aplica +20% de potência e consumo em ambos.")
        return embed

    def refresh_items(self):
        self.clear_items()
        if self.tecnicas:
            self.add_item(KidoTechniqueSelect(self))

        single_disabled = len(self.selected_tecnicas()) != 1
        encantamento = ui.Button(label="Encantamento", style=discord.ButtonStyle.secondary, row=1, disabled=single_disabled)
        encantamento.callback = self.use_encantamento
        sem_encantamento = ui.Button(label="Sem Encantamento", style=discord.ButtonStyle.secondary, row=1, disabled=single_disabled)
        sem_encantamento.callback = self.use_sem_encantamento
        self.add_item(encantamento)
        self.add_item(sem_encantamento)

        if self.allow_niju and len(self.tecnicas) >= 2:
            niju = ui.Button(label="Nijū Eishō", style=discord.ButtonStyle.secondary, row=1, disabled=len(self.selected_tecnicas()) != 2)
            niju.callback = self.use_niju
            self.add_item(niju)

        if self.selected_ids:
            clear_selection = ui.Button(label="Limpar seleção", style=discord.ButtonStyle.secondary, row=2)
            clear_selection.callback = self.clear_selection
            self.add_item(clear_selection)

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

    async def _use_single(self, interaction, metodo):
        if not await self._guard(interaction):
            return
        selected = self.selected_tecnicas()
        if len(selected) != 1:
            return await interaction.response.edit_message(embed=self.build_embed("❌ Selecione exatamente 1 Kidō para este método."), view=self)
        ok, msg, data = use_kido_tecnica(self.user_id, selected[0]["id"], metodo)
        if not ok:
            return await interaction.response.edit_message(embed=self.build_embed(f"❌ {msg}"), view=self)
        await interaction.response.edit_message(
            embed=build_use_embed(data),
            view=KidoStatusReturnView(self.user_id, self.from_profile, self.profile_layout),
        )

    async def use_encantamento(self, interaction):
        await self._use_single(interaction, "encantamento")

    async def use_sem_encantamento(self, interaction):
        await self._use_single(interaction, "sem_encantamento")

    async def use_niju(self, interaction):
        if not await self._guard(interaction):
            return
        selected = self.selected_tecnicas()
        if len(selected) != 2:
            return await interaction.response.edit_message(embed=self.build_embed("❌ Selecione exatamente 2 Kidō para usar Nijū Eishō."), view=self)
        ok, msg, data = use_niju_eisho(self.user_id, [tecnica["id"] for tecnica in selected])
        if not ok:
            return await interaction.response.edit_message(embed=self.build_embed(f"❌ {msg}"), view=self)
        await interaction.response.edit_message(
            embed=build_use_embed(data),
            view=KidoStatusReturnView(self.user_id, self.from_profile, self.profile_layout),
        )

    async def voltar_status(self, interaction):
        if not await self._guard(interaction):
            return
        await edit_kido_status_message(interaction, self.user_id, self.from_profile, self.profile_layout)

    async def clear_selection(self, interaction):
        if not await self._guard(interaction):
            return
        self.selected_ids = []
        self.refresh_items()
        await interaction.response.edit_message(embed=self.build_embed("Nenhum Kidō selecionado."), view=self)

    async def prev_page(self, interaction):
        if not await self._guard(interaction):
            return
        self.page = max(0, self.page - 1)
        self.refresh_items()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def next_page(self, interaction):
        if not await self._guard(interaction):
            return
        self.page = min(self.max_page, self.page + 1)
        self.refresh_items()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class KidoMenuView(ui.View):
    def __init__(self, user_id, bot, from_profile=False, profile_layout="desktop"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.bot = bot
        self.from_profile = from_profile
        self.profile_layout = profile_layout
        if not from_profile:
            for item in list(self.children):
                if getattr(item, "label", None) == "Perfil":
                    self.remove_item(item)

    @ui.button(label="Status", style=discord.ButtonStyle.success, row=1)
    async def status(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        await edit_kido_status_message(interaction, self.user_id, self.from_profile, self.profile_layout)

    @ui.button(label="Usar", style=discord.ButtonStyle.success, row=1)
    async def usar_kido(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        view = KidoUseMenuView(self.user_id, self.from_profile, self.profile_layout)
        await interaction.response.edit_message(
            embed=build_kido_use_menu_embed(view),
            attachments=[],
            view=view,
        )

    @ui.button(label="Kidō Oficiais", style=discord.ButtonStyle.secondary, row=0)
    async def oficiais(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        embed, _ = build_list_embed("oficial", self.user_id, known_only=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Kidō Criados", style=discord.ButtonStyle.secondary, row=0)
    async def criados(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        embed, _ = build_list_embed("criado", self.user_id, include_private=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Kidō Exclusivos", style=discord.ButtonStyle.secondary, row=0)
    async def exclusivos(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        embed, _ = build_list_embed("exclusivo", include_private=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Kidō Proibidos", style=discord.ButtonStyle.danger, row=0)
    async def proibidos(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        embed, _ = build_list_embed("proibido", include_private=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Perfil", style=discord.ButtonStyle.secondary, row=1)
    async def perfil(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        from cogs.player_system import PerfilView, build_profile_image_embed, _resolve_member

        member = _resolve_member(interaction.client, interaction.guild, self.user_id)
        file, embed = await build_profile_image_embed(self.user_id, member, self.profile_layout)
        if not file:
            return await interaction.response.send_message("❌ Personagem não encontrado.", ephemeral=True)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=PerfilView(self.user_id, self.profile_layout))


class KidoListView(ui.View):
    def __init__(self, classificacao="oficial", page=0):
        super().__init__(timeout=120)
        self.classificacao = classificacao
        self.page = page
        self._sync_nav_buttons()

    def _sync_nav_buttons(self):
        total = len(list_kido_tecnicas(self.classificacao, include_private=True))
        max_page = max(0, (total - 1) // 10)
        self.page = max(0, min(self.page, max_page))
        self.prev_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= max_page

    async def _show(self, interaction, classificacao=None, page=None):
        if classificacao is not None:
            self.classificacao = classificacao
            self.page = 0
        if page is not None:
            self.page = page
        self._sync_nav_buttons()
        embed, _ = build_list_embed(self.classificacao, include_private=True, page=self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Kidō Oficiais", style=discord.ButtonStyle.primary)
    async def oficiais(self, interaction, button):
        await self._show(interaction, "oficial")

    @ui.button(label="Kidō Criados", style=discord.ButtonStyle.primary)
    async def criados(self, interaction, button):
        await self._show(interaction, "criado")

    @ui.button(label="Kidō Exclusivos", style=discord.ButtonStyle.secondary)
    async def exclusivos(self, interaction, button):
        await self._show(interaction, "exclusivo")

    @ui.button(label="Kidō Proibidos", style=discord.ButtonStyle.danger)
    async def proibidos(self, interaction, button):
        await self._show(interaction, "proibido")

    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction, button):
        await self._show(interaction, page=self.page - 1)

    @ui.button(label="➡️", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction, button):
        await self._show(interaction, page=self.page + 1)


class KidoUseMenuView(ui.View):
    def __init__(self, user_id, from_profile=False, profile_layout="desktop"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.from_profile = from_profile
        self.profile_layout = profile_layout
        self.known_by_class = {
            classificacao: list_known_kido_tecnicas(user_id, classificacao)
            for classificacao in ("oficial", "criado", "exclusivo", "proibido")
        }
        self._add_class_button("oficial")
        self._add_class_button("criado")
        kaido = ui.Button(label="Kaidō", style=discord.ButtonStyle.secondary, row=0)
        kaido.callback = self.open_kaido
        self.add_item(kaido)
        self._add_class_button("exclusivo")
        self._add_class_button("proibido")
        voltar_status = ui.Button(label="Voltar ao Status", style=discord.ButtonStyle.secondary, row=1)
        voltar_status.callback = self.voltar_status
        self.add_item(voltar_status)

    @property
    def has_categories(self):
        return bool(self.children)

    def _add_class_button(self, classificacao):
        if not self.known_by_class.get(classificacao):
            return
        button = ui.Button(
            label=KIDO_CLASSIFICATION_LABELS[classificacao],
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        button.callback = self._make_category_callback(classificacao)
        self.add_item(button)

    def _make_category_callback(self, classificacao):
        async def callback(interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
            tecnicas = list_known_kido_tecnicas(self.user_id, classificacao)
            if not tecnicas:
                embed = discord.Embed(
                    title="🔮 Usar Kidō",
                    description="❌ Você não possui Kidō disponível nesta classificação.",
                    color=0x7f8cff,
                )
                return await interaction.response.edit_message(embed=embed, view=self)
            view = KidoUseListView(
                self.user_id,
                classificacao,
                tecnicas,
                self.from_profile,
                self.profile_layout,
            )
            await interaction.response.edit_message(embed=view.build_embed(), view=view)

        return callback

    async def open_kaido(self, interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        view = KidoKaidoActionView(self.user_id, self.from_profile, self.profile_layout)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    async def voltar_status(self, interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Este menu não é seu.", ephemeral=True)
        await edit_kido_status_message(interaction, self.user_id, self.from_profile, self.profile_layout)


class KidoInfoSelect(ui.Select):
    def __init__(self, user_id, classificacao, tecnicas):
        options = [
            discord.SelectOption(
                label=f"{t['categoria']} #{t['numero']} - {t['nome']}"[:100],
                value=str(index),
                description=(t["descricao"] or "Sem descrição")[:100],
            )
            for index, t in enumerate(tecnicas[:25])
        ]
        super().__init__(placeholder="Escolha um Kidō para ver detalhes...", options=options)
        self.user_id = user_id
        self.classificacao = classificacao
        self.tecnicas = tecnicas[:25]

    async def callback(self, interaction):
        tecnica = self.tecnicas[int(self.values[0])]
        data = calculate_kido(interaction.user.id, tecnica["numero"])
        embed = discord.Embed(title=f"{tecnica['categoria']} #{tecnica['numero']} — {tecnica['nome']}", color=0x7f8cff)
        embed.description = tecnica["descricao"] or "Sem descrição cadastrada."
        embed.add_field(name="Classificação", value=f"`{tecnica['classificacao']}`", inline=True)
        embed.add_field(name="Cooldown", value=f"`{data['cooldown']}` turno(s)", inline=True)
        if tecnica.get("dano_bonus") is not None:
            embed.add_field(name="Bônus da técnica", value=f"`+{int(float(tecnica['dano_bonus']) * 100)}%`", inline=True)
        embed.add_field(name="Gasto estimado", value=f"`{data['cost']}` Reiryoku", inline=True)
        await interaction.response.edit_message(embed=embed, view=KidoInfoDetailView(self.user_id, self.classificacao))


class KidoInfoDetailView(ui.View):
    def __init__(self, user_id, classificacao):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.classificacao = classificacao

    @ui.button(label="Voltar", style=discord.ButtonStyle.secondary)
    async def voltar(self, interaction, button):
        tecnicas = list_kido_tecnicas(self.classificacao, include_private=True)
        embed, _ = build_list_embed(self.classificacao, include_private=True)
        view = ui.View(timeout=120)
        if tecnicas:
            view.add_item(KidoInfoSelect(interaction.user.id, self.classificacao, tecnicas))
        await interaction.response.edit_message(embed=embed, view=view)


class KidoInfoMenuView(ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def _show(self, interaction, classificacao):
        tecnicas = list_kido_tecnicas(classificacao, include_private=True)
        embed, _ = build_list_embed(classificacao, include_private=True)
        view = ui.View(timeout=120)
        if tecnicas:
            view.add_item(KidoInfoSelect(self.user_id, classificacao, tecnicas))
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Oficiais", style=discord.ButtonStyle.primary)
    async def oficiais(self, interaction, button):
        await self._show(interaction, "oficial")

    @ui.button(label="Exclusivos", style=discord.ButtonStyle.secondary)
    async def exclusivos(self, interaction, button):
        await self._show(interaction, "exclusivo")

    @ui.button(label="Proibidos", style=discord.ButtonStyle.danger)
    async def proibidos(self, interaction, button):
        await self._show(interaction, "proibido")


class KidoSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="kido", aliases=["kidō", "kidos", "kidōs"], invoke_without_command=True)
    async def kido(self, ctx):
        if not has_kido_access(ctx.author.id):
            return await ctx.send(KIDO_ACCESS_ERROR)
        file, embed = await build_kido_image_embed(ctx.author.id, ctx.author)
        if not embed:
            return await ctx.send("❌ Você não possui um personagem.")
        await ctx.send(file=file, embed=embed, view=KidoMenuView(ctx.author.id, self.bot))

    @commands.command(name="kido_criar", aliases=["kidō_criar", "kidos_criar", "kidōs_criar"])
    async def kido_criar(self, ctx):
        if not has_kido_access(ctx.author.id):
            return await ctx.send(KIDO_ACCESS_ERROR)
        view = KidoCreateMenuView(ctx.author.id, ctx.author.guild_permissions.administrator)
        await ctx.send(embed=view.build_embed(), view=view)

    @commands.command(name="info_kido", aliases=["info_kidō", "info_kidos", "info_kidōs"])
    async def info_kido(self, ctx):
        if not has_kido_access(ctx.author.id):
            return await ctx.send(KIDO_ACCESS_ERROR)
        embed = discord.Embed(
            title="📚 Informações de Kidō",
            description="Escolha uma categoria para abrir a lista e ver detalhes de cooldown, buff e efeito.",
            color=0x7f8cff,
        )
        await ctx.send(embed=embed, view=KidoInfoMenuView(ctx.author.id))

    @commands.command(name="setar_bonus_kido")
    @commands.has_permissions(administrator=True)
    async def setar_bonus_kido(self, ctx, kido_id: int, bonus: str = None):
        parsed = None if bonus in (None, "remover", "limpar", "none", "0") else parse_percent(bonus)
        if bonus not in (None, "remover", "limpar", "none", "0") and parsed is None:
            return await ctx.send("❌ Bônus inválido. Use `50` para +50%, ou `remover` para limpar.")
        if parsed is not None and parsed > 3:
            return await ctx.send("❌ Bônus alto demais. Use até 300%.")

        with get_connection() as conn:
            row = conn.execute("SELECT nome FROM kido_tecnicas WHERE id = ?", (kido_id,)).fetchone()
            if not row:
                return await ctx.send("❌ Kidō não encontrado.")
            conn.execute("UPDATE kido_tecnicas SET dano_bonus = ? WHERE id = ?", (parsed, kido_id))
            conn.commit()

        value = "sem bônus" if parsed is None else f"+{int(parsed * 100)}%"
        await ctx.send(f"✅ Bônus de `{row[0]}` ajustado para **{value}**.")

    @commands.command(name="dar_kido", aliases=["setar_kido"])
    @commands.has_permissions(administrator=True)
    async def dar_kido(self, ctx, membro: discord.Member, kido_id: int):
        ok, msg, granted_id = grant_kido_tecnica(membro.id, kido_id)
        prefix = "✅" if ok else "❌"
        extra = f" ID atribuído `{granted_id}`." if ok and granted_id else ""
        await ctx.send(f"{prefix} {msg}{extra}")

    @commands.command(name="listar_kido", aliases=["listar_kidō", "listar_kidos", "listar_kidōs"])
    async def listar_kido(self, ctx):
        if not has_kido_access(ctx.author.id):
            return await ctx.send(KIDO_ACCESS_ERROR)
        embed = discord.Embed(
            title="📚 Lista de Kidō",
            description="Escolha a classificação que deseja consultar.",
            color=0x95a5ff,
        )
        await ctx.send(embed=embed, view=KidoListView())

    @kido.command(name="simular")
    async def simular(self, ctx, numero: int, metodo: str = "normal"):
        await self.enviar_simulacao(ctx, numero, metodo)

    async def enviar_simulacao(self, ctx, numero, metodo="normal"):
        if not has_kido_access(ctx.author.id):
            return await ctx.send(KIDO_ACCESS_ERROR)
        if numero < 1 or numero > 99:
            return await ctx.send("❌ O número do Kidō deve ficar entre 1 e 99.")
        data = calculate_kido(ctx.author.id, numero, metodo)
        embed = discord.Embed(title=f"🧮 Simulação de Kidō #{numero}", color=0x95a5ff)
        embed.add_field(name="Tier", value=f"`{data['tier']}/6`", inline=True)
        embed.add_field(name="Acesso", value=f"`#1 ao #{data['max_number']}`", inline=True)
        embed.add_field(name="Método", value=f"`{data['method']}`", inline=True)
        embed.add_field(name="Gasto", value=f"`{data['cost']}` Reiryoku", inline=True)
        embed.add_field(name="Ajuste", value=f"`{_format_method_adjustment(data)}`", inline=True)
        embed.add_field(name="Cooldown", value=f"`{data['cooldown']}` turno(s)", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="kido_simular", aliases=["kidō_simular", "kidos_simular", "kidōs_simular"])
    async def kido_simular(self, ctx, numero: int, metodo: str = "normal"):
        await self.enviar_simulacao(ctx, numero, metodo)



async def setup(bot):
    await bot.add_cog(KidoSystem(bot))
