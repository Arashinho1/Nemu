import discord
from discord.ext import commands
from discord import ui
import sqlite3
from database import get_connection
from utils.ui_components import PaginatorView
from cogs.potencial_system import ModalConsumoPotencial, PotencialAttrScopeView
from utils.race_restrictions import normalize_race_restriction
from utils.logic import atribuir_vaga_logica, remover_vaga_logica
from utils.tecnica_service import configure_tecnica_buff, list_tecnicas


RACE_CATEGORIES = {"Raças Iniciais", "Raças Normais", "Raças Especiais"}
VAGA_EDIT_COLUMNS = "nome, categoria, atributo, limite, restricao_raca, role_id, vaga_id, descricao"
PONTO_COLUMNS = "nome, categoria, vaga_id, pontos_pa_bonus, pontos_pp_bonus, pontos_pa_inicial, pontos_pp_inicial"


def parse_vaga_id_limite(value):
    parts = [x.strip() for x in value.split(',')]
    vaga_id = parts[0] if parts else ""
    if not vaga_id:
        raise ValueError("Informe o ID da vaga.")
    limite = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    return vaga_id, limite


def parse_restricao_raca(value):
    return normalize_race_restriction(value)


def format_role_label(guild, role_id):
    if not role_id:
        return "Nenhum"
    role = guild.get_role(int(role_id))
    return f"@{role.name}" if role else f"ID {role_id} (não encontrado)"


def parse_optional_points(value, label):
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        number = int(text)
    except ValueError:
        raise ValueError(f"{label} precisa ser um número inteiro.")
    if number < 0:
        raise ValueError(f"{label} não pode ser negativo.")
    return number


def format_points(pa, pp):
    parts = []
    if pa:
        parts.append(f"PA `{pa}`")
    if pp:
        parts.append(f"PP `{pp}`")
    return " | ".join(parts) if parts else "Nenhum"


def format_removed_vagas(removed):
    if not removed:
        return "Nenhuma vaga removida."
    lines = []
    for item in removed:
        points = format_points(item.get("pontos_pa", 0), item.get("pontos_pp", 0))
        point_text = "" if points == "Nenhum" else f" | Pontos removidos: {points}"
        lines.append(f"• `{item['nome']}`{point_text}")
    return "\n".join(lines)


def format_vinculo_mode(extra):
    return "Extra (não ocupa vaga)" if extra else "Conta como vaga"


def get_vaga_for_edit(vaga_id):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        vaga = conn.execute(
            f"SELECT {VAGA_EDIT_COLUMNS} FROM vagas WHERE vaga_id = ?",
            (vaga_id,),
        ).fetchone()
    return dict(vaga) if vaga else None


def get_vaga_nome_by_ref(vaga_ref):
    with get_connection() as conn:
        row = conn.execute(
            'SELECT nome FROM vagas WHERE vaga_id = ? OR nome = ?',
            (vaga_ref, vaga_ref),
        ).fetchone()
    return row[0] if row else None


def get_vaga_categories():
    with get_connection() as conn:
        return [row[0] for row in conn.execute(
            '''
            SELECT DISTINCT categoria
            FROM vagas
            WHERE categoria IS NOT NULL AND categoria != ''
            ORDER BY categoria COLLATE NOCASE
            '''
        ).fetchall()]


def get_vagas_by_category(categoria):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT nome, categoria, vaga_id
            FROM vagas
            WHERE categoria = ?
            ORDER BY nome COLLATE NOCASE
            ''',
            (categoria,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_vinculos():
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT vv.vaga_pai, vv.vaga_filha, vv.extra,
                   pai.vaga_id AS pai_id, filha.vaga_id AS filha_id
            FROM vagas_vinculo vv
            LEFT JOIN vagas pai ON vv.vaga_pai = pai.nome
            LEFT JOIN vagas filha ON vv.vaga_filha = filha.nome
            ORDER BY vv.vaga_pai COLLATE NOCASE, vv.vaga_filha COLLATE NOCASE
            '''
        ).fetchall()
    return [dict(row) for row in rows]


class ModalCriarVaga(ui.Modal, title='Detalhes da Vaga'):
    nome = ui.TextInput(label='Nome da Vaga', placeholder='Ex: Manipulação Perfeita')
    descricao = ui.TextInput(label='Descrição da Vaga (Opcional)', placeholder='Explique a vaga ou cole o link da thread', style=discord.TextStyle.paragraph, required=False)
    atributos = ui.TextInput(label='Atributos Afetados', placeholder='Ex: forca,velocidade ou todos', default='todos')
    restricoes = ui.TextInput(label='Restrição de Raça', placeholder='Ex: Shinigami, Vaizard ou Todos', required=False)
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
            placeholder='Ex: Shinigami, Vaizard ou Todos',
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
                    conn.execute('UPDATE player_vagas SET origem_vaga = ? WHERE origem_vaga = ?', (novo_nome, self.original_nome))
                    conn.execute('UPDATE player_vaga_pontos SET vaga_nome = ? WHERE vaga_nome = ?', (novo_nome, self.original_nome))
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

    @ui.button(label="🎚️ Mult. de Potencial", style=discord.ButtonStyle.secondary)
    async def mult_potencial(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar potenciais.", ephemeral=True)
        await interaction.response.send_message(
            "Escolha como configurar os multiplicadores por atributo:",
            view=PotencialAttrScopeView(),
            ephemeral=True,
        )


class ModalSetarPontos(ui.Modal):
    def __init__(self, vaga, modo):
        title = "Pontos Bônus da Vaga" if modo == "bonus" else "Pontos Iniciais da Raça"
        super().__init__(title=title)
        self.vaga = vaga
        self.modo = modo

        pa_key = "pontos_pa_bonus" if modo == "bonus" else "pontos_pa_inicial"
        pp_key = "pontos_pp_bonus" if modo == "bonus" else "pontos_pp_inicial"
        pa_atual = int(vaga.get(pa_key) or 0)
        pp_atual = int(vaga.get(pp_key) or 0)
        pa_label = "PA bônus" if modo == "bonus" else "PA inicial"
        pp_label = "PP bônus" if modo == "bonus" else "PP inicial"

        self.pa = ui.TextInput(
            label=pa_label,
            placeholder="Opcional. Ex: 10",
            required=False,
            default=str(pa_atual) if pa_atual else "",
        )
        self.pp = ui.TextInput(
            label=pp_label,
            placeholder="Opcional. Ex: 5",
            required=False,
            default=str(pp_atual) if pp_atual else "",
        )
        self.add_item(self.pa)
        self.add_item(self.pp)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar pontos.", ephemeral=True)

        try:
            pa = parse_optional_points(self.pa.value, "PA")
            pp = parse_optional_points(self.pp.value, "PP")
        except ValueError as exc:
            return await interaction.response.send_message(f"❌ {exc}", ephemeral=True)

        pa_col = "pontos_pa_bonus" if self.modo == "bonus" else "pontos_pa_inicial"
        pp_col = "pontos_pp_bonus" if self.modo == "bonus" else "pontos_pp_inicial"
        with get_connection() as conn:
            conn.execute(
                f"UPDATE vagas SET {pa_col} = ?, {pp_col} = ? WHERE nome = ?",
                (pa, pp, self.vaga["nome"]),
            )
            conn.commit()

        tipo = "bônus" if self.modo == "bonus" else "iniciais"
        await interaction.response.send_message(
            f"✅ Pontos {tipo} de `{self.vaga['nome']}` atualizados: {format_points(pa, pp)}.",
            ephemeral=True,
        )


class SelectSetarPontoVaga(ui.Select):
    def __init__(self, vagas, modo, start_index=0):
        self.vagas = {str(start_index + index): vaga for index, vaga in enumerate(vagas)}
        self.modo = modo
        options = []
        for index, vaga in enumerate(vagas, start=start_index):
            vid = vaga["vaga_id"] or "Sem ID"
            if modo == "bonus":
                points = format_points(vaga["pontos_pa_bonus"], vaga["pontos_pp_bonus"])
            else:
                points = format_points(vaga["pontos_pa_inicial"], vaga["pontos_pp_inicial"])
            options.append(discord.SelectOption(
                label=f"{vid} - {vaga['nome']}"[:100],
                value=str(index),
                description=f"Pontos: {points}"[:100],
            ))
        placeholder = "Escolha a vaga..." if modo == "bonus" else "Escolha a raça inicial..."
        super().__init__(placeholder=placeholder, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar pontos.", ephemeral=True)
        vaga = self.vagas[self.values[0]]
        await interaction.response.send_modal(ModalSetarPontos(vaga, self.modo))


class SetarPontoVagaView(ui.View):
    def __init__(self, vagas, modo):
        super().__init__(timeout=120)
        for start in range(0, min(len(vagas), 125), 25):
            self.add_item(SelectSetarPontoVaga(vagas[start:start + 25], modo, start))


class SelectSetarPontoCategoria(ui.Select):
    def __init__(self, categorias):
        options = [discord.SelectOption(label=categoria, value=categoria) for categoria in categorias[:25]]
        super().__init__(placeholder="Escolha a categoria da vaga...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar pontos.", ephemeral=True)

        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            vagas = conn.execute(
                f"SELECT {PONTO_COLUMNS} FROM vagas WHERE categoria = ? ORDER BY nome COLLATE NOCASE",
                (self.values[0],),
            ).fetchall()

        if not vagas:
            return await interaction.response.send_message("❌ Categoria vazia.", ephemeral=True)

        await interaction.response.send_message(
            "Selecione a vaga para configurar PA/PP bônus:",
            view=SetarPontoVagaView([dict(vaga) for vaga in vagas], "bonus"),
            ephemeral=True,
        )


class SetarPontoCategoriaView(ui.View):
    def __init__(self, categorias):
        super().__init__(timeout=120)
        self.add_item(SelectSetarPontoCategoria(categorias))


class SetarPontoMenuView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="Pontos de Vaga", style=discord.ButtonStyle.primary)
    async def pontos_vaga(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar pontos.", ephemeral=True)
        with get_connection() as conn:
            categorias = [row[0] for row in conn.execute(
                '''
                SELECT DISTINCT categoria
                FROM vagas
                WHERE categoria IS NOT NULL
                  AND categoria != ''
                  AND categoria != 'Raças Iniciais'
                ORDER BY categoria COLLATE NOCASE
                '''
            ).fetchall()]
        if not categorias:
            return await interaction.response.send_message("❌ Nenhuma vaga cadastrada fora de raças iniciais.", ephemeral=True)
        await interaction.response.send_message(
            "Selecione a categoria para configurar PA/PP bônus:",
            view=SetarPontoCategoriaView(categorias),
            ephemeral=True,
        )

    @ui.button(label="Pontos Iniciais", style=discord.ButtonStyle.success)
    async def pontos_iniciais(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar pontos.", ephemeral=True)
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            racas = conn.execute(
                f"SELECT {PONTO_COLUMNS} FROM vagas WHERE categoria = ? ORDER BY nome COLLATE NOCASE",
                ("Raças Iniciais",),
            ).fetchall()
        if not racas:
            return await interaction.response.send_message("❌ Nenhuma raça inicial cadastrada.", ephemeral=True)
        await interaction.response.send_message(
            "Selecione a raça para configurar PA/PP iniciais:",
            view=SetarPontoVagaView([dict(raca) for raca in racas], "inicial"),
            ephemeral=True,
        )


class SelectVinculoCategoria(ui.Select):
    def __init__(self, categorias, etapa, vaga_pai=None):
        self.etapa = etapa
        self.vaga_pai = vaga_pai
        options = [discord.SelectOption(label=categoria[:100], value=categoria) for categoria in categorias[:25]]
        placeholder = "Categoria da vaga mãe..." if etapa == "pai" else "Categoria da vaga filha..."
        super().__init__(placeholder=placeholder, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem vincular vagas.", ephemeral=True)

        vagas = get_vagas_by_category(self.values[0])
        if not vagas:
            return await interaction.response.send_message("❌ Categoria vazia.", ephemeral=True)

        texto = "Escolha a vaga mãe:" if self.etapa == "pai" else f"Vaga mãe: `{self.vaga_pai}`\nEscolha a vaga filha:"
        await interaction.response.send_message(
            texto,
            view=VinculoVagaSelectView(vagas, self.etapa, self.vaga_pai),
            ephemeral=True,
        )


class VinculoCategoriaView(ui.View):
    def __init__(self, categorias, etapa, vaga_pai=None):
        super().__init__(timeout=120)
        self.add_item(SelectVinculoCategoria(categorias, etapa, vaga_pai))


class SelectVinculoVaga(ui.Select):
    def __init__(self, vagas, etapa, vaga_pai=None, start_index=0):
        self.vagas = {str(start_index + index): vaga for index, vaga in enumerate(vagas)}
        self.etapa = etapa
        self.vaga_pai = vaga_pai
        options = []
        for index, vaga in enumerate(vagas, start=start_index):
            vid = vaga["vaga_id"] or "Sem ID"
            options.append(discord.SelectOption(
                label=f"{vid} - {vaga['nome']}"[:100],
                value=str(index),
                description=(vaga["categoria"] or "Sem categoria")[:100],
            ))
        placeholder = "Escolha a vaga mãe..." if etapa == "pai" else "Escolha a vaga filha..."
        super().__init__(placeholder=placeholder, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem vincular vagas.", ephemeral=True)

        vaga = self.vagas[self.values[0]]
        if self.etapa == "pai":
            categorias = get_vaga_categories()
            if not categorias:
                return await interaction.response.send_message("❌ Nenhuma vaga cadastrada.", ephemeral=True)
            return await interaction.response.send_message(
                f"Vaga mãe escolhida: `{vaga['nome']}`\nAgora escolha a categoria da vaga filha:",
                view=VinculoCategoriaView(categorias, "filha", vaga["nome"]),
                ephemeral=True,
            )

        if vaga["nome"] == self.vaga_pai:
            return await interaction.response.send_message("❌ A vaga filha não pode ser a mesma vaga mãe.", ephemeral=True)

        await interaction.response.send_message(
            f"Vaga mãe: `{self.vaga_pai}`\nVaga filha: `{vaga['nome']}`\nComo essa vaga filha deve contar?",
            view=VinculoModoView(self.vaga_pai, vaga["nome"]),
            ephemeral=True,
        )


class VinculoVagaSelectView(ui.View):
    def __init__(self, vagas, etapa, vaga_pai=None):
        super().__init__(timeout=120)
        for start in range(0, min(len(vagas), 125), 25):
            self.add_item(SelectVinculoVaga(vagas[start:start + 25], etapa, vaga_pai, start))


class VinculoModoView(ui.View):
    def __init__(self, vaga_pai, vaga_filha):
        super().__init__(timeout=120)
        self.vaga_pai = vaga_pai
        self.vaga_filha = vaga_filha

    async def salvar(self, interaction: discord.Interaction, extra):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem vincular vagas.", ephemeral=True)

        with get_connection() as conn:
            conn.execute(
                '''
                INSERT OR REPLACE INTO vagas_vinculo (vaga_pai, vaga_filha, extra)
                VALUES (?, ?, ?)
                ''',
                (self.vaga_pai, self.vaga_filha, 1 if extra else 0),
            )
            conn.commit()

        await interaction.response.send_message(
            f"✅ Vínculo salvo: `{self.vaga_pai}` dá `{self.vaga_filha}`.\n"
            f"Modo da filha: **{format_vinculo_mode(extra)}**.",
            ephemeral=True,
        )

    @ui.button(label="Conta como vaga", style=discord.ButtonStyle.primary)
    async def conta_como_vaga(self, interaction: discord.Interaction, button: ui.Button):
        await self.salvar(interaction, extra=False)

    @ui.button(label="Extra", style=discord.ButtonStyle.success)
    async def extra(self, interaction: discord.Interaction, button: ui.Button):
        await self.salvar(interaction, extra=True)


class SelectRemoverVinculo(ui.Select):
    def __init__(self, vinculos, start_index=0):
        self.vinculos = {str(start_index + index): vinculo for index, vinculo in enumerate(vinculos)}
        options = []
        for index, vinculo in enumerate(vinculos, start=start_index):
            pai_id = vinculo["pai_id"] or "Sem ID"
            filha_id = vinculo["filha_id"] or "Sem ID"
            options.append(discord.SelectOption(
                label=f"{pai_id} -> {filha_id}"[:100],
                value=str(index),
                description=f"{vinculo['vaga_pai']} dá {vinculo['vaga_filha']} | {format_vinculo_mode(vinculo['extra'])}"[:100],
            ))
        super().__init__(placeholder="Escolha o vínculo para remover...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem remover vínculos.", ephemeral=True)

        vinculo = self.vinculos[self.values[0]]
        with get_connection() as conn:
            conn.execute(
                'DELETE FROM vagas_vinculo WHERE vaga_pai = ? AND vaga_filha = ?',
                (vinculo["vaga_pai"], vinculo["vaga_filha"]),
            )
            conn.commit()

        await interaction.response.send_message(
            f"✅ Vínculo removido: `{vinculo['vaga_pai']}` não dá mais `{vinculo['vaga_filha']}`.",
            ephemeral=True,
        )


class RemoverVinculoView(ui.View):
    def __init__(self, vinculos):
        super().__init__(timeout=120)
        for start in range(0, min(len(vinculos), 125), 25):
            self.add_item(SelectRemoverVinculo(vinculos[start:start + 25], start))


class VincularVagaMenuView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="Criar vínculo", style=discord.ButtonStyle.primary)
    async def criar_vinculo(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem vincular vagas.", ephemeral=True)
        categorias = get_vaga_categories()
        if not categorias:
            return await interaction.response.send_message("❌ Nenhuma vaga cadastrada.", ephemeral=True)
        await interaction.response.send_message(
            "Escolha a categoria da vaga mãe:",
            view=VinculoCategoriaView(categorias, "pai"),
            ephemeral=True,
        )

    @ui.button(label="Listar vínculos", style=discord.ButtonStyle.secondary)
    async def listar_vinculos(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem listar vínculos.", ephemeral=True)
        vinculos = get_vinculos()
        if not vinculos:
            return await interaction.response.send_message("Nenhum vínculo cadastrado.", ephemeral=True)

        embeds = []
        current = discord.Embed(title="🔗 Vínculos de Vagas", color=0x3498db)
        lines = []
        for vinculo in vinculos:
            pai_id = vinculo["pai_id"] or "Sem ID"
            filha_id = vinculo["filha_id"] or "Sem ID"
            lines.append(
                f"• `{pai_id}` **{vinculo['vaga_pai']}** dá `{filha_id}` **{vinculo['vaga_filha']}** "
                f"- {format_vinculo_mode(vinculo['extra'])}"
            )
            if len(lines) == 12:
                current.description = "\n".join(lines)
                embeds.append(current)
                current = discord.Embed(title="🔗 Vínculos de Vagas (cont.)", color=0x3498db)
                lines = []
        if lines:
            current.description = "\n".join(lines)
            embeds.append(current)

        if len(embeds) > 1:
            await interaction.response.send_message(embed=embeds[0], view=PaginatorView(embeds), ephemeral=True)
        else:
            await interaction.response.send_message(embed=embeds[0], ephemeral=True)

    @ui.button(label="Remover vínculo", style=discord.ButtonStyle.danger)
    async def remover_vinculo(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem remover vínculos.", ephemeral=True)
        vinculos = get_vinculos()
        if not vinculos:
            return await interaction.response.send_message("Nenhum vínculo cadastrado.", ephemeral=True)
        await interaction.response.send_message(
            "Escolha o vínculo que deseja remover:",
            view=RemoverVinculoView(vinculos),
            ephemeral=True,
        )


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
                vgs = conn.execute('''
                    SELECT nome, multiplicador, bonus_fixo, atributo, limite, restricao_raca,
                           vaga_id, descricao, pontos_pa_bonus, pontos_pp_bonus,
                           pontos_pa_inicial, pontos_pp_inicial
                    FROM vagas
                    WHERE categoria = ?
                ''', (cat,)).fetchall()
            else: 
                # Lista Geral: Filtra para não mostrar as raças iniciais aqui
                vgs = conn.execute('''
                    SELECT nome, multiplicador, bonus_fixo, atributo, limite, restricao_raca,
                           vaga_id, descricao, pontos_pa_bonus, pontos_pp_bonus,
                           pontos_pa_inicial, pontos_pp_inicial
                    FROM vagas
                    WHERE categoria != "Raças Iniciais"
                ''').fetchall()
            
            if not vgs: return await interaction.response.send_message("❌ Categoria vazia.", ephemeral=True)

            title = f"📋 Vagas: {cat or 'Geral'}"
            embeds = []
            current_embed = discord.Embed(title=title, color=0x9b59b6)

            for v in vgs:
                nome, mult, fixo, attr, limite, rest, vid, desc = v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7]
                pa_bonus, pp_bonus, pa_inicial, pp_inicial = v[8], v[9], v[10], v[11]
                # Buscar ocupantes
                cursor = conn.cursor()
                cursor.execute('''SELECT pv.user_id, p.nome FROM player_vagas pv
                                  LEFT JOIN personagens p ON pv.user_id = p.user_id
                                  WHERE pv.vaga_nome = ?
                                    AND COALESCE(pv.extra, 0) = 0''', (nome,))
                ocupantes = [f"<@{row[0]}>" for row in cursor.fetchall()]
                
                lim_str = f"{len(ocupantes)}/{limite}" if limite > 0 else f"{len(ocupantes)}/∞"
                pontos_label = "iniciais" if cat == "Raças Iniciais" else "bônus"
                pontos_valor = (
                    format_points(pa_inicial, pp_inicial)
                    if cat == "Raças Iniciais"
                    else format_points(pa_bonus, pp_bonus)
                )
                info = f"**ID:** `{vid}` | **Buff:** `x{mult}/+{fixo}`\n"
                info += f"**Ocupação:** `{lim_str}`\n"
                info += f"**Pontos {pontos_label}:** {pontos_valor}\n"
                info += f"**Descrição:** {desc if desc else '*Sem descrição*'}\n"
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
            v = conn.execute('''
                SELECT nome, categoria, atributo, multiplicador, bonus_fixo, limite,
                       restricao_raca, descricao, pontos_pa_bonus, pontos_pp_bonus,
                       pontos_pa_inicial, pontos_pp_inicial
                FROM vagas
                WHERE vaga_id = ?
            ''', (vaga_id,)).fetchone()
            vinculos = conn.execute(
                '''
                SELECT filha.nome, filha.vaga_id, vv.extra
                FROM vagas_vinculo vv
                JOIN vagas filha ON vv.vaga_filha = filha.nome
                WHERE vv.vaga_pai = ?
                ORDER BY filha.nome COLLATE NOCASE
                ''',
                (v[0],) if v else ("",),
            ).fetchall()
        
        if not v:
            return await ctx.send("❌ Vaga não encontrada.")
        
        nome, cat, attr, mult, fixo, lim, rest, desc, pa_bonus, pp_bonus, pa_inicial, pp_inicial = v
        embed = discord.Embed(title=f"📝 Detalhes: {nome}", color=0x3498db)
        embed.add_field(name="📁 Categoria", value=cat, inline=True)
        embed.add_field(name="🆔 ID", value=vaga_id, inline=True)
        embed.add_field(name="📊 Buffs", value=f"Multiplicador: `{mult}`\nFixo: `{fixo}`\nAlvo: `{attr}`", inline=False)
        if cat == "Raças Iniciais":
            embed.add_field(name="🎁 Pontos iniciais", value=format_points(pa_inicial, pp_inicial), inline=True)
        else:
            embed.add_field(name="🎁 Pontos bônus", value=format_points(pa_bonus, pp_bonus), inline=True)
        embed.add_field(name="🚫 Restrições", value=f"Raça: `{rest}`\nLimite: `{lim}`", inline=True)
        
        desc_val = desc if desc else "Sem descrição definida."
        embed.add_field(name="📖 Descrição / Thread", value=desc_val, inline=False)
        if vinculos:
            filhos = [
                f"`{vid or 'Sem ID'}` {filha} - {format_vinculo_mode(extra)}"
                for filha, vid, extra in vinculos
            ]
            embed.add_field(name="🔗 Vagas vinculadas", value="\n".join(filhos)[:1024], inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(help="(Admin) Define os bônus matemáticos de uma vaga.")
    @commands.has_permissions(administrator=True)
    async def buffar(self, ctx):
        await ctx.send("Abra o menu para configurar bônus ou consumo:", view=BuffarMenuView())

    @commands.command(name="setar_ponto", help="(Admin) Configura PA/PP bônus de vagas e PA/PP iniciais de raças.")
    @commands.has_permissions(administrator=True)
    async def setar_ponto(self, ctx):
        embed = discord.Embed(title="🎁 Configurar Pontos", color=0xf1c40f)
        embed.description = (
            "Escolha se deseja configurar pontos bônus de vagas ou pontos iniciais das raças cadastradas."
        )
        await ctx.send(embed=embed, view=SetarPontoMenuView())

    @commands.command(name="vincular_vaga", help="(Admin) Vincula uma vaga mãe a vagas filhas.")
    @commands.has_permissions(administrator=True)
    async def vincular_vaga(self, ctx):
        embed = discord.Embed(title="🔗 Vincular Vagas", color=0x3498db)
        embed.description = (
            "Crie vínculos do tipo `vaga mãe dá vaga filha` e escolha se a filha conta como vaga ou entra como extra."
        )
        await ctx.send(embed=embed, view=VincularVagaMenuView())

    @commands.command(name="dar_vaga", aliases=["setar_vaga"], help="(Admin) Atribui uma vaga a um jogador. Uso: .dar_vaga @membro ID ou nome")
    @commands.has_permissions(administrator=True)
    async def dar_vaga(self, ctx, membro: discord.Member, *, vaga_ref: str):
        vaga_nome = get_vaga_nome_by_ref(vaga_ref.strip())
        if not vaga_nome:
            return await ctx.send("❌ Vaga não encontrada. Use o ID ou o nome exato.")

        sucesso, msg = await atribuir_vaga_logica(ctx.guild, membro, vaga_nome)
        await ctx.send(f"{'✅' if sucesso else '❌'} {membro.mention}: {msg} `{vaga_nome}`")

    @commands.command(name="remover_vaga", aliases=["tirar_vaga"], help="(Admin) Remove uma vaga de um jogador. Uso: .remover_vaga @membro ID ou nome")
    @commands.has_permissions(administrator=True)
    async def remover_vaga(self, ctx, membro: discord.Member, *, vaga_ref: str):
        vaga_nome = get_vaga_nome_by_ref(vaga_ref.strip())
        if not vaga_nome:
            return await ctx.send("❌ Vaga não encontrada. Use o ID ou o nome exato.")

        sucesso, msg, removed = await remover_vaga_logica(ctx.guild, membro, vaga_nome)
        if not sucesso:
            return await ctx.send(msg)

        await ctx.send(
            f"✅ Vaga removida de {membro.mention}.\n"
            f"{format_removed_vagas(removed)}"
        )

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
