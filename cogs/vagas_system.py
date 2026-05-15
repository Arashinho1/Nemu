import discord
from discord.ext import commands
from discord import ui
import sqlite3
from database import get_connection
from utils.ui_components import PaginatorView
from cogs.potencial_system import ModalConsumoPotencial
from utils.tecnica_service import configure_tecnica_buff, list_tecnicas


RACE_CATEGORIES = {"Raças Iniciais", "Raças Normais", "Raças Especiais"}
VAGA_EDIT_COLUMNS = "nome, categoria, atributo, limite, restricao_raca, role_id, vaga_id, descricao"


def parse_vaga_id_limite(value):
    parts = [x.strip() for x in value.split(',')]
    vaga_id = parts[0] if parts else ""
    if not vaga_id:
        raise ValueError("Informe o ID da vaga.")
    limite = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    return vaga_id, limite


def parse_restricao_raca(value):
    if not value:
        return "Nenhuma"
    parts = [x.strip() for x in value.split(",")]
    return parts[0] or "Nenhuma"


def format_role_label(guild, role_id):
    if not role_id:
        return "Nenhum"
    role = guild.get_role(int(role_id))
    return f"@{role.name}" if role else f"ID {role_id} (não encontrado)"


def get_vaga_for_edit(vaga_id):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        vaga = conn.execute(
            f"SELECT {VAGA_EDIT_COLUMNS} FROM vagas WHERE vaga_id = ?",
            (vaga_id,),
        ).fetchone()
    return dict(vaga) if vaga else None


class ModalCriarVaga(ui.Modal, title='Detalhes da Vaga'):
    nome = ui.TextInput(label='Nome da Vaga', placeholder='Ex: Manipulação Perfeita')
    descricao = ui.TextInput(label='Descrição da Vaga (Opcional)', placeholder='Explique a vaga ou cole o link da thread', style=discord.TextStyle.paragraph, required=False)
    atributos = ui.TextInput(label='Atributos Afetados', placeholder='Ex: forca,velocidade ou todos', default='todos')
    restricoes = ui.TextInput(label='Restrição de Raça', placeholder='Ex: Shinigami (Use Nenhuma se não houver)', required=False)
    v_id_limite = ui.TextInput(label='ID e Limite', placeholder='Ex: R01, 5')

    def __init__(self, categoria, role_id=None):
        super().__init__()
        self.categoria = categoria
        self.role_id = role_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            v_id_val, lim = parse_vaga_id_limite(self.v_id_limite.value)
            raca_res = parse_restricao_raca(self.restricoes.value)

            with get_connection() as conn:
                conn.execute('''INSERT OR REPLACE INTO vagas 
                    (nome, categoria, atributo, limite, restricao_raca, role_id, vaga_id, descricao) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (self.nome.value, self.categoria, self.atributos.value.lower(), lim, raca_res, self.role_id, v_id_val, self.descricao.value or ""))
            await interaction.response.send_message(f"✅ Vaga `{self.nome.value}` criada em `{self.categoria}`!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erro ao processar dados: {e}", ephemeral=True)

class ModalEditarVaga(ui.Modal, title='Editar Vaga'):
    def __init__(self, vaga, role_id=None):
        super().__init__()
        self.original_nome = vaga["nome"]
        self.original_vaga_id = vaga["vaga_id"]
        self.categoria = vaga["categoria"]
        self.role_id = role_id

        self.nome = ui.TextInput(label='Nome da Vaga', placeholder='Ex: Manipulação Perfeita', default=vaga["nome"])
        self.descricao = ui.TextInput(
            label='Descrição da Vaga (Opcional)',
            placeholder='Explique a vaga ou cole o link da thread',
            style=discord.TextStyle.paragraph,
            required=False,
            default=vaga["descricao"] or "",
        )
        self.atributos = ui.TextInput(
            label='Atributos Afetados',
            placeholder='Ex: forca,velocidade ou todos',
            default=vaga["atributo"] or "todos",
        )
        self.restricoes = ui.TextInput(
            label='Restrição de Raça',
            placeholder='Ex: Shinigami (Use Nenhuma se não houver)',
            required=False,
            default=vaga["restricao_raca"] or "Nenhuma",
        )
        self.v_id_limite = ui.TextInput(
            label='ID e Limite',
            placeholder='Ex: R01, 5',
            default=f"{vaga['vaga_id']}, {vaga['limite'] or 0}",
        )

        self.add_item(self.nome)
        self.add_item(self.descricao)
        self.add_item(self.atributos)
        self.add_item(self.restricoes)
        self.add_item(self.v_id_limite)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            novo_nome = self.nome.value.strip()
            if not novo_nome:
                return await interaction.response.send_message("❌ O nome da vaga não pode ficar vazio.", ephemeral=True)

            novo_vaga_id, novo_limite = parse_vaga_id_limite(self.v_id_limite.value)
            raca_res = parse_restricao_raca(self.restricoes.value)

            with get_connection() as conn:
                conn.execute('''
                    UPDATE vagas
                    SET nome = ?, atributo = ?, limite = ?, restricao_raca = ?, role_id = ?, vaga_id = ?, descricao = ?
                    WHERE nome = ?
                ''', (
                    novo_nome,
                    self.atributos.value.lower(),
                    novo_limite,
                    raca_res,
                    self.role_id,
                    novo_vaga_id,
                    self.descricao.value or "",
                    self.original_nome,
                ))

                if novo_nome != self.original_nome:
                    conn.execute('UPDATE player_vagas SET vaga_nome = ? WHERE vaga_nome = ?', (novo_nome, self.original_nome))
                    conn.execute('UPDATE vagas_vinculo SET vaga_pai = ? WHERE vaga_pai = ?', (novo_nome, self.original_nome))
                    conn.execute('UPDATE vagas_vinculo SET vaga_filha = ? WHERE vaga_filha = ?', (novo_nome, self.original_nome))
                    if self.categoria in RACE_CATEGORIES:
                        conn.execute('UPDATE personagens SET raca = ? WHERE raca = ?', (novo_nome, self.original_nome))

                conn.commit()
            await interaction.response.send_message(f"✅ Vaga `{self.original_nome}` atualizada!", ephemeral=True)
        except sqlite3.IntegrityError:
            await interaction.response.send_message("❌ Já existe uma vaga com esse nome ou ID.", ephemeral=True)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erro ao processar dados: {e}", ephemeral=True)

class ModalBuffarVaga(ui.Modal):
    def __init__(self, vaga_ref=""):
        super().__init__(title='Configurar Buffs da Vaga')
        self.v_id = ui.TextInput(label='ID ou Nome da Vaga', placeholder='Ex: R01 ou Shinigami', default=vaga_ref or "")
        self.mult = ui.TextInput(label='Multiplicador (Ex: 0.2 para +20%)', default='0.0')
        self.fixo = ui.TextInput(label='Bônus Fixo', default='0')
        self.attr = ui.TextInput(label='Atributo (forca, velocidade, todos)', default='todos')
        self.add_item(self.v_id)
        self.add_item(self.mult)
        self.add_item(self.fixo)
        self.add_item(self.attr)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            with get_connection() as conn:
                # Procura por ID primeiro, depois por nome
                vaga = conn.execute('SELECT nome FROM vagas WHERE vaga_id = ? OR nome = ?', (self.v_id.value, self.v_id.value)).fetchone()
                if not vaga:
                    return await interaction.response.send_message("❌ Vaga não encontrada.", ephemeral=True)

                conn.execute('''UPDATE vagas SET multiplicador = ?, bonus_fixo = ?, atributo = ? 
                                WHERE nome = ?''', (float(self.mult.value), int(self.fixo.value), self.attr.value.lower(), vaga[0]))
                conn.commit()
            await interaction.response.send_message(f"✅ Buffs de `{vaga[0]}` configurados!", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Multiplicador ou bônus fixo inválido.", ephemeral=True)


class ModalBuffarTecnica(ui.Modal):
    def __init__(self, tecnica_id=""):
        super().__init__(title='Configurar Buffs da Técnica')
        self.tecnica_id = ui.TextInput(label='ID da Técnica', placeholder='Ex: 12', default=str(tecnica_id or ""))
        self.mult = ui.TextInput(label='Multiplicador (Ex: 0.2 para +20%)', default='0.0')
        self.fixo = ui.TextInput(label='Bônus Fixo', default='0')
        self.attr = ui.TextInput(label='Atributo físico', placeholder='forca, velocidade, resistencia ou todos', default='todos')
        self.dur_cd = ui.TextInput(label='Duração e Cooldown', placeholder='Ex: 2, 1', default='1, 1')
        self.add_item(self.tecnica_id)
        self.add_item(self.mult)
        self.add_item(self.fixo)
        self.add_item(self.attr)
        self.add_item(self.dur_cd)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            tecnica_id = int(self.tecnica_id.value)
            parts = [part.strip() for part in self.dur_cd.value.split(",")]
            duracao = int(parts[0]) if parts and parts[0] else 1
            cooldown = int(parts[1]) if len(parts) > 1 and parts[1] else 1
        except ValueError:
            return await interaction.response.send_message("❌ ID, duração ou cooldown inválido.", ephemeral=True)

        ok, msg, _ = configure_tecnica_buff(
            tecnica_id,
            self.mult.value,
            self.fixo.value,
            self.attr.value,
            duracao,
            cooldown,
        )
        await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)


class SelectCategoriaBuffVaga(ui.Select):
    def __init__(self, categorias):
        options = [discord.SelectOption(label=categoria, value=categoria) for categoria in categorias[:25]]
        super().__init__(placeholder="Escolha a categoria da vaga...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar buffs.", ephemeral=True)

        categoria = self.values[0]
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            vagas = conn.execute(
                "SELECT nome, vaga_id, atributo, multiplicador, bonus_fixo FROM vagas WHERE categoria = ? ORDER BY nome COLLATE NOCASE",
                (categoria,),
            ).fetchall()
        if not vagas:
            return await interaction.response.send_message("❌ Categoria vazia.", ephemeral=True)
        await interaction.response.send_message(
            "Selecione a vaga para configurar:",
            view=SelectVagaBuffView([dict(vaga) for vaga in vagas]),
            ephemeral=True,
        )


class SelectVagaBuff(ui.Select):
    def __init__(self, vagas):
        self.vagas = {str(index): vaga for index, vaga in enumerate(vagas)}
        options = []
        for index, vaga in enumerate(vagas):
            vid = vaga["vaga_id"] or "Sem ID"
            options.append(discord.SelectOption(
                label=f"{vid} - {vaga['nome']}"[:100],
                value=str(index),
                description=f"Buff: x{vaga['multiplicador']}/+{vaga['bonus_fixo']} | {vaga['atributo'] or 'todos'}"[:100],
            ))
        super().__init__(placeholder="Escolha a vaga...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar buffs.", ephemeral=True)
        vaga = self.vagas[self.values[0]]
        await interaction.response.send_modal(ModalBuffarVaga(vaga["vaga_id"] or vaga["nome"]))


class SelectVagaBuffView(ui.View):
    def __init__(self, vagas):
        super().__init__(timeout=120)
        self.add_item(SelectVagaBuff(vagas[:25]))


class BuffVagaCategoriaView(ui.View):
    def __init__(self, categorias):
        super().__init__(timeout=120)
        self.add_item(SelectCategoriaBuffVaga(categorias))


class SelectClassificacaoBuffTecnica(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Técnicas Oficiais", value="oficial"),
            discord.SelectOption(label="Técnicas Criadas", value="criado"),
        ]
        super().__init__(placeholder="Escolha a categoria de técnica...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar buffs.", ephemeral=True)
        tecnicas = list_tecnicas(self.values[0], include_private=True)
        if not tecnicas:
            return await interaction.response.send_message("❌ Nenhuma técnica cadastrada nesta categoria.", ephemeral=True)
        await interaction.response.send_message(
            "Selecione a técnica para configurar:",
            view=SelectTecnicaBuffView(tecnicas),
            ephemeral=True,
        )


class SelectTecnicaBuff(ui.Select):
    def __init__(self, tecnicas):
        self.tecnicas = {str(index): tecnica for index, tecnica in enumerate(tecnicas)}
        options = []
        for index, tecnica in enumerate(tecnicas[:25]):
            mult = int(float(tecnica.get("multiplicador") or 0) * 100)
            fixo = int(tecnica.get("bonus_fixo") or 0)
            options.append(discord.SelectOption(
                label=f"ID {tecnica['id']} - {tecnica['nome']}"[:100],
                value=str(index),
                description=f"{tecnica['categoria']} | +{mult}%/+{fixo} | {tecnica.get('atributo') or 'todos'}"[:100],
            ))
        super().__init__(placeholder="Escolha a técnica...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar buffs.", ephemeral=True)
        tecnica = self.tecnicas[self.values[0]]
        await interaction.response.send_modal(ModalBuffarTecnica(tecnica["id"]))


class SelectTecnicaBuffView(ui.View):
    def __init__(self, tecnicas):
        super().__init__(timeout=120)
        self.add_item(SelectTecnicaBuff(tecnicas[:25]))


class BuffTecnicaCategoriaView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(SelectClassificacaoBuffTecnica())


class BuffarMenuView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="⚙️ Buffs de Vaga", style=discord.ButtonStyle.primary)
    async def buffs_vaga(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar buffs.", ephemeral=True)
        with get_connection() as conn:
            categorias = [row[0] for row in conn.execute(
                "SELECT DISTINCT categoria FROM vagas WHERE categoria IS NOT NULL AND categoria != '' ORDER BY categoria COLLATE NOCASE"
            ).fetchall()]
        if not categorias:
            return await interaction.response.send_modal(ModalBuffarVaga())
        await interaction.response.send_message("Selecione a categoria da vaga:", view=BuffVagaCategoriaView(categorias), ephemeral=True)

    @ui.button(label="⚔️ Buffs de Técnica", style=discord.ButtonStyle.primary)
    async def buffs_tecnica(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar buffs.", ephemeral=True)
        await interaction.response.send_message("Selecione a categoria da técnica:", view=BuffTecnicaCategoriaView(), ephemeral=True)

    @ui.button(label="🔥 Consumo de Potencial", style=discord.ButtonStyle.secondary)
    async def consumo_potencial(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar consumo.", ephemeral=True)
        await interaction.response.send_modal(ModalConsumoPotencial())


class SelectCargoVaga(ui.RoleSelect):
    def __init__(self, parent_view, placeholder):
        super().__init__(placeholder=placeholder, min_values=0, max_values=1)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selected_role_id = self.values[0].id if self.values else None
        await interaction.response.defer()


class CriarVagaCargoView(ui.View):
    def __init__(self, categoria):
        super().__init__(timeout=120)
        self.categoria = categoria
        self.selected_role_id = None
        self.add_item(SelectCargoVaga(self, "Selecione o cargo vinculado (opcional)..."))

    @ui.button(label="Continuar", style=discord.ButtonStyle.success)
    async def continuar(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem criar vagas.", ephemeral=True)
        await interaction.response.send_modal(ModalCriarVaga(self.categoria, self.selected_role_id))


class EditarVagaCargoView(ui.View):
    def __init__(self, vaga):
        super().__init__(timeout=120)
        self.vaga = vaga
        self.selected_role_id = vaga["role_id"]
        self.add_item(SelectCargoVaga(self, "Selecione um novo cargo ou continue para manter..."))

    @ui.button(label="Continuar", style=discord.ButtonStyle.primary)
    async def continuar(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem editar vagas.", ephemeral=True)
        await interaction.response.send_modal(ModalEditarVaga(self.vaga, self.selected_role_id))

    @ui.button(label="Remover Cargo", style=discord.ButtonStyle.secondary)
    async def remover_cargo(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem editar vagas.", ephemeral=True)
        await interaction.response.send_modal(ModalEditarVaga(self.vaga, None))


class SelectCategoriaVaga(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Títulos", value="Titulos"),
            discord.SelectOption(label="Zanpakuto", value="Zanpakuto"),
            discord.SelectOption(label="Linhagens", value="Linhagens"),
            discord.SelectOption(label="Raças Especiais", value="Raças Especiais"),
            discord.SelectOption(label="Características", value="Características"),
        ]
        super().__init__(placeholder="Escolha a categoria da nova vaga...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem criar vagas.", ephemeral=True)
        await interaction.response.send_message(
            "Selecione o cargo vinculado a esta vaga. Se não houver cargo, clique em continuar.",
            view=CriarVagaCargoView(self.values[0]),
            ephemeral=True,
        )


class SelectCategoriaEditarVaga(ui.Select):
    def __init__(self, categorias):
        options = [discord.SelectOption(label=categoria, value=categoria) for categoria in categorias[:25]]
        super().__init__(placeholder="Escolha a categoria da vaga...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem editar vagas.", ephemeral=True)

        categoria = self.values[0]
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            vagas = conn.execute(
                f"SELECT {VAGA_EDIT_COLUMNS} FROM vagas WHERE categoria = ? ORDER BY nome COLLATE NOCASE",
                (categoria,),
            ).fetchall()

        if not vagas:
            return await interaction.response.send_message("❌ Categoria vazia.", ephemeral=True)

        await interaction.response.send_message(
            "Selecione a vaga que deseja editar:",
            view=EditarVagaSelectView([dict(vaga) for vaga in vagas]),
            ephemeral=True,
        )


class SelectEditarVaga(ui.Select):
    def __init__(self, vagas, start_index=0):
        self.vagas = {str(start_index + index): vaga for index, vaga in enumerate(vagas)}
        options = []
        for index, vaga in enumerate(vagas, start=start_index):
            vid = vaga["vaga_id"] or "Sem ID"
            label = f"{vid} - {vaga['nome']}"[:100]
            description = f"Limite: {vaga['limite'] or 0} | Atributos: {vaga['atributo'] or 'todos'}"[:100]
            options.append(discord.SelectOption(label=label, value=str(index), description=description))
        super().__init__(placeholder=f"Vagas {start_index + 1}-{start_index + len(vagas)}", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem editar vagas.", ephemeral=True)
        vaga = self.vagas[self.values[0]]
        await interaction.response.send_message(
            f"Cargo atual: **{format_role_label(interaction.guild, vaga['role_id'])}**.\n"
            "Selecione um novo cargo, continue para manter ou remova o cargo.",
            view=EditarVagaCargoView(vaga),
            ephemeral=True,
        )


class EditarVagaSelectView(ui.View):
    def __init__(self, vagas):
        super().__init__(timeout=120)
        for start in range(0, min(len(vagas), 125), 25):
            self.add_item(SelectEditarVaga(vagas[start:start + 25], start))


class VagasView(ui.View):
    def __init__(self, is_admin=False):
        super().__init__(timeout=None)
        if is_admin:
            btn = ui.Button(label="➕ Criar Vaga", style=discord.ButtonStyle.success, custom_id="admin_criar_vaga")
            btn.callback = self.admin_criar_vaga_callback
            self.add_item(btn)
            btn_edit = ui.Button(label="✏️ Editar Vaga", style=discord.ButtonStyle.primary, custom_id="admin_editar_vaga")
            btn_edit.callback = self.admin_editar_vaga_callback
            self.add_item(btn_edit)

    async def admin_criar_vaga_callback(self, interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem criar vagas.", ephemeral=True)
        view = ui.View()
        view.add_item(SelectCategoriaVaga())
        await interaction.response.send_message("Selecione a categoria para começar:", view=view, ephemeral=True)

    async def admin_editar_vaga_callback(self, interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem editar vagas.", ephemeral=True)
        with get_connection() as conn:
            categorias = [row[0] for row in conn.execute(
                'SELECT DISTINCT categoria FROM vagas ORDER BY categoria COLLATE NOCASE'
            ).fetchall() if row[0]]

        if not categorias:
            return await interaction.response.send_message("❌ Nenhuma vaga cadastrada.", ephemeral=True)

        view = ui.View(timeout=120)
        view.add_item(SelectCategoriaEditarVaga(categorias))
        await interaction.response.send_message("Selecione a categoria da vaga que deseja editar:", view=view, ephemeral=True)

    async def listar_por_cat(self, interaction, cat):
        with get_connection() as conn:
            if cat: 
                vgs = conn.execute('SELECT nome, multiplicador, bonus_fixo, atributo, limite, restricao_raca, vaga_id FROM vagas WHERE categoria = ?', (cat,)).fetchall()
            else: 
                # Lista Geral: Filtra para não mostrar as raças iniciais aqui
                vgs = conn.execute('SELECT nome, multiplicador, bonus_fixo, atributo, limite, restricao_raca, vaga_id FROM vagas WHERE categoria != "Raças Iniciais"').fetchall()
            
            if not vgs: return await interaction.response.send_message("❌ Categoria vazia.", ephemeral=True)

            title = f"📋 Vagas: {cat or 'Geral'}"
            embeds = []
            current_embed = discord.Embed(title=title, color=0x9b59b6)

            for v in vgs:
                nome, mult, fixo, attr, limite, rest, vid = v[0], v[1], v[2], v[3], v[4], v[5], v[6]
                # Buscar ocupantes
                cursor = conn.cursor()
                cursor.execute('''SELECT p.nome FROM player_vagas pv 
                                  JOIN personagens p ON pv.user_id = p.user_id 
                                  WHERE pv.vaga_nome = ?''', (nome,))
                ocupantes = [row[0] for row in cursor.fetchall()]
                
                lim_str = f"{len(ocupantes)}/{limite}" if limite > 0 else f"{len(ocupantes)}/∞"
                info = f"**ID:** `{vid}` | **Buff:** `x{mult}/+{fixo}`\n"
                info += f"**Ocupação:** `{lim_str}`\n"
                info += f"👤: {', '.join(ocupantes) if ocupantes else '*Vazia*'}"

                if len(current_embed.fields) == 10:
                    embeds.append(current_embed)
                    current_embed = discord.Embed(title=f"{title} (cont.)", color=0x9b59b6)
                current_embed.add_field(name=f"🔹 {nome}", value=info, inline=False)

            if current_embed.fields:
                embeds.append(current_embed)

            if len(embeds) > 1:
                await interaction.response.send_message(embed=embeds[0], view=PaginatorView(embeds), ephemeral=True)
            else:
                await interaction.response.send_message(embed=embeds[0], ephemeral=True)

    @ui.button(label="Títulos", style=discord.ButtonStyle.secondary)
    async def t(self, interaction, button): await self.listar_por_cat(interaction, "Titulos")

    @ui.button(label="Zanpakuto", style=discord.ButtonStyle.secondary)
    async def z(self, interaction, button): await self.listar_por_cat(interaction, "Zanpakuto")

    @ui.button(label="Linhagens", style=discord.ButtonStyle.secondary)
    async def l(self, interaction, button): await self.listar_por_cat(interaction, "Linhagens")

    @ui.button(label="Raças Esp.", style=discord.ButtonStyle.secondary)
    async def re(self, interaction, button): await self.listar_por_cat(interaction, "Raças Especiais")

    @ui.button(label="Características", style=discord.ButtonStyle.secondary)
    async def c(self, interaction, button): await self.listar_por_cat(interaction, "Características")

    @ui.button(label="Gerais", style=discord.ButtonStyle.secondary)
    async def g(self, interaction, button): await self.listar_por_cat(interaction, None)

class VagasSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(help="Lista todas as vagas.")
    async def vagas(self, ctx):
        await ctx.send("🏛️ Registro de Vagas", view=VagasView(ctx.author.guild_permissions.administrator))

    @commands.command(help="Mostra informações detalhadas de uma vaga pelo ID.")
    async def info(self, ctx, vaga_id: str):
        with get_connection() as conn:
            v = conn.execute('SELECT nome, categoria, atributo, multiplicador, bonus_fixo, limite, restricao_raca, descricao FROM vagas WHERE vaga_id = ?', (vaga_id,)).fetchone()
        
        if not v:
            return await ctx.send("❌ Vaga não encontrada.")
        
        nome, cat, attr, mult, fixo, lim, rest, desc = v
        embed = discord.Embed(title=f"📝 Detalhes: {nome}", color=0x3498db)
        embed.add_field(name="📁 Categoria", value=cat, inline=True)
        embed.add_field(name="🆔 ID", value=vaga_id, inline=True)
        embed.add_field(name="📊 Buffs", value=f"Multiplicador: `{mult}`\nFixo: `{fixo}`\nAlvo: `{attr}`", inline=False)
        embed.add_field(name="🚫 Restrições", value=f"Raça: `{rest}`\nLimite: `{lim}`", inline=True)
        
        desc_val = desc if desc else "Sem descrição definida."
        embed.add_field(name="📖 Descrição / Thread", value=desc_val, inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(help="(Admin) Define os bônus matemáticos de uma vaga.")
    @commands.has_permissions(administrator=True)
    async def buffar(self, ctx):
        await ctx.send("Abra o menu para configurar bônus ou consumo:", view=BuffarMenuView())

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.data and interaction.data.get('custom_id') == "btn_buffar":
            if not interaction.user.guild_permissions.administrator:
                return await interaction.response.send_message("❌ Apenas administradores podem configurar buffs.", ephemeral=True)
            await interaction.response.send_modal(ModalBuffarVaga())
        if interaction.data and interaction.data.get('custom_id') == "btn_consumo_potencial":
            if not interaction.user.guild_permissions.administrator:
                return await interaction.response.send_message("❌ Apenas administradores podem configurar consumo.", ephemeral=True)
            await interaction.response.send_modal(ModalConsumoPotencial())

    @commands.group(name="inicial", invoke_without_command=True, help="(Admin) Gerencia as raças iniciais.")
    @commands.has_permissions(administrator=True)
    async def inicial(self, ctx):
        if ctx.invoked_subcommand is None:
            await self.config(ctx)

    @inicial.command(name="config", help="Abre o menu de configuração das raças iniciais.")
    @commands.has_permissions(administrator=True)
    async def config(self, ctx):
        with get_connection() as conn:
            races = conn.execute('SELECT nome, vaga_id FROM vagas WHERE categoria = "Raças Iniciais"').fetchall()

        view = ui.View()
        
        if races:
            select = ui.Select(placeholder="Selecione uma raça inicial para editar...")
            for nome, vid in races:
                select.add_option(label=nome, value=vid, description=f"ID: {vid}")
            
            async def select_callback(interaction: discord.Interaction):
                if not interaction.user.guild_permissions.administrator:
                    return await interaction.response.send_message("❌ Apenas administradores podem configurar raças iniciais.", ephemeral=True)
                vaga = get_vaga_for_edit(select.values[0])
                if not vaga:
                    return await interaction.response.send_message("❌ Vaga não encontrada.", ephemeral=True)
                await interaction.response.send_message(
                    f"Cargo atual: **{format_role_label(interaction.guild, vaga['role_id'])}**.\n"
                    "Selecione um novo cargo, continue para manter ou remova o cargo.",
                    view=EditarVagaCargoView(vaga),
                    ephemeral=True,
                )
            
            select.callback = select_callback
            view.add_item(select)

        btn_add = ui.Button(label="➕ Adicionar Nova Raça", style=discord.ButtonStyle.success)
        async def add_cb(interaction: discord.Interaction):
            if not interaction.user.guild_permissions.administrator:
                return await interaction.response.send_message("❌ Apenas administradores podem configurar raças iniciais.", ephemeral=True)
            await interaction.response.send_message(
                "Selecione o cargo vinculado a esta raça inicial. Se não houver cargo, clique em continuar.",
                view=CriarVagaCargoView("Raças Iniciais"),
                ephemeral=True,
            )
        
        btn_add.callback = add_cb
        view.add_item(btn_add)
        
        await ctx.send("⚙️ **Configuração de Raças Iniciais**\nSelecione uma raça na lista para editar ou adicione uma nova:", view=view)

async def setup(bot):
    await bot.add_cog(VagasSystem(bot))
