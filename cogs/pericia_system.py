import discord
import sqlite3
from discord.ext import commands
from discord import ui
from database import get_connection
from utils.history_log import send_points_history
from utils.permissions import guild_owner_only
from utils.pericia_service import (
    VALID_TARGETS,
    add_pericia_race_inheritance,
    build_pericia_raca_filter,
    format_bonus,
    format_pericia_target,
    get_accessible_pericia_racas,
    list_pericia_race_inheritance,
    normalize_pericia_target,
    remove_pericia_race_inheritance,
)

def get_proximo_custo(nivel_atual):
    if nivel_atual >= 6: return None
    # Nível 1 -> 2: 100 | 2 -> 3: 150 | 3 -> 4: 225...
    return int(100 * (1.5 ** (nivel_atual - 1)))


def _parse_optional_bonus(value):
    text = (value or "").strip().replace(",", ".")
    if not text:
        return None, None
    try:
        return float(text), None
    except ValueError:
        return None, "❌ Bônus deve ser decimal. Exemplo: `0.05`, ou deixe vazio para não usar bônus."


def _parse_optional_attr(value):
    attr = normalize_pericia_target(value)
    if not attr:
        if (value or "").strip():
            return None, (
                "❌ Alvo inválido. Use atributos como `forca`, `velocidade`, `resistencia`, "
                "`reiryoku`, `reiatsu`, `kido`, combinações físicas, `tecnica:Cero` ou `turnos:Máscara`."
            )
        return None, None
    return attr, None


def _format_admin_bonus(bonus_valor, atributo_afetado):
    if bonus_valor is None or not atributo_afetado:
        return "sem bônus"
    if str(atributo_afetado).startswith("turnos:"):
        return f"{float(bonus_valor):g}/lvl em `{format_pericia_target(atributo_afetado)}`"
    return f"{int(float(bonus_valor) * 100)}%/lvl em `{format_pericia_target(atributo_afetado)}`"

class PericiaView(ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def update_embed(self, interaction):
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            p = conn.execute('SELECT raca, pontos_pericia FROM personagens WHERE user_id = ?', (self.user_id,)).fetchone()
            racas = get_accessible_pericia_racas(self.user_id, conn, p['raca'])
            raca_filter, raca_params = build_pericia_raca_filter("pb.raca", racas)
            pericias = conn.execute(f'''
                SELECT pb.id, pb.nome, pb.descricao, pb.bonus_valor, pb.atributo_afetado, pp.nivel
                FROM pericias_base pb
                LEFT JOIN player_pericias pp ON pb.id = pp.pericia_id AND pp.user_id = ?
                WHERE {raca_filter}
            ''', (self.user_id, *raca_params)).fetchall()

        embed = discord.Embed(title="📊 Suas Perícias", color=0x2b2d31)
        embed.description = f"Pontos de Perícia (PP) Disponíveis: `{p['pontos_pericia']}`\n\u200b"
        
        self.clear_items()
        for peri in pericias:
            lvl = peri['nivel'] if peri['nivel'] else 1
            custo = get_proximo_custo(lvl)
            custo_str = f"Custo: {custo} PP" if custo else "Nível Máximo"
            bonus_text = format_bonus(peri)
            
            field_val = f"┣ Nível: **{lvl}/6**\n┣ Bônus: `{bonus_text}`\n┗ {custo_str}"
            embed.add_field(name=f"🔸 {peri['nome']}", value=field_val, inline=True)

            if custo:
                btn = ui.Button(label=f"Subir {peri['nome']}", style=discord.ButtonStyle.primary, custom_id=f"up_{peri['id']}")
                btn.callback = self.make_callback(peri['id'], custo, lvl)
                self.add_item(btn)

        await interaction.response.edit_message(embed=embed, view=self)

    def make_callback(self, peri_id, custo, nivel_atual):
        async def callback(interaction: discord.Interaction):
            with get_connection() as conn:
                p = conn.execute('SELECT pontos_pericia FROM personagens WHERE user_id = ?', (self.user_id,)).fetchone()
                if p[0] < custo:
                    return await interaction.response.send_message(f"❌ Você precisa de {custo} PP.", ephemeral=True)
                pericia_nome = conn.execute('SELECT nome FROM pericias_base WHERE id = ?', (peri_id,)).fetchone()

                conn.execute('UPDATE personagens SET pontos_pericia = pontos_pericia - ? WHERE user_id = ?', (custo, self.user_id))
                conn.execute('''INSERT OR REPLACE INTO player_pericias (user_id, pericia_id, nivel) 
                                VALUES (?, ?, ?)''', (self.user_id, peri_id, nivel_atual + 1))
                conn.commit()
            await send_points_history(
                interaction.client,
                action="Distribuição",
                point_type="Pontos de Perícia (PP)",
                quantity=custo,
                giver=interaction.user,
                receiver=interaction.user,
                source_channel=interaction.channel,
                details={
                    "pool_label": "PP disponíveis",
                    "pool_before": p[0],
                    "pool_after": p[0] - custo,
                    "target_label": pericia_nome[0] if pericia_nome else f"Perícia {peri_id}",
                    "target_before": f"Nv {nivel_atual}",
                    "target_after": f"Nv {nivel_atual + 1}",
                },
            )
            await self.update_embed(interaction)
        return callback

class ModalCriarPericia(ui.Modal, title='Nova Perícia'):
    nome = ui.TextInput(label='Nome (ex: Zanjutsu)')
    raca = ui.TextInput(label='Raça (conforme cadastrada ou "Todas")')
    desc = ui.TextInput(label='Descrição', style=discord.TextStyle.paragraph)
    bonus = ui.TextInput(label='Bônus por Nível (opcional)', placeholder='Ex: 0.05 para 5%', required=False)
    attr = ui.TextInput(
        label='Atributo afetado (opcional)',
        placeholder='forca, kido, tecnica:Cero, turnos:Máscara...',
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        bonus, error = _parse_optional_bonus(self.bonus.value)
        if error:
            return await interaction.response.send_message(error, ephemeral=True)
        attr, error = _parse_optional_attr(self.attr.value)
        if error:
            return await interaction.response.send_message(error, ephemeral=True)
        if bonus is None or attr is None:
            bonus = None
            attr = None

        with get_connection() as conn:
            conn.execute('''INSERT INTO pericias_base (nome, raca, descricao, bonus_valor, atributo_afetado) 
                            VALUES (?, ?, ?, ?, ?)''', 
                            (self.nome.value, self.raca.value, self.desc.value, bonus, attr))
            conn.commit()
        await interaction.response.send_message(f"✅ Perícia `{self.nome.value}` criada para `{self.raca.value}`!", ephemeral=True)

class ModalEditarPericia(ui.Modal, title='Editar Perícia'):
    def __init__(self, pericia):
        super().__init__()
        self.pericia_id = pericia['id']
        self.nome = ui.TextInput(label='Nome', default=pericia['nome'])
        self.raca = ui.TextInput(label='Raça', default=pericia['raca'])
        self.desc = ui.TextInput(label='Descrição', style=discord.TextStyle.paragraph, default=pericia['descricao'] or '')
        bonus_default = "" if pericia['bonus_valor'] is None else str(pericia['bonus_valor'])
        attr_default = pericia['atributo_afetado'] or ""
        self.bonus = ui.TextInput(label='Bônus por Nível (opcional)', placeholder='Ex: 0.05 para 5%', default=bonus_default, required=False)
        self.attr = ui.TextInput(
            label='Atributo afetado (opcional)',
            placeholder='forca, kido, tecnica:Cero, turnos:Máscara...',
            default=attr_default,
            required=False,
        )
        self.add_item(self.nome)
        self.add_item(self.raca)
        self.add_item(self.desc)
        self.add_item(self.bonus)
        self.add_item(self.attr)

    async def on_submit(self, interaction: discord.Interaction):
        bonus, error = _parse_optional_bonus(self.bonus.value)
        if error:
            return await interaction.response.send_message(error, ephemeral=True)
        attr, error = _parse_optional_attr(self.attr.value)
        if error:
            return await interaction.response.send_message(error, ephemeral=True)
        if bonus is None or attr is None:
            bonus = None
            attr = None

        with get_connection() as conn:
            conn.execute(
                '''
                UPDATE pericias_base
                SET nome = ?, raca = ?, descricao = ?, bonus_valor = ?, atributo_afetado = ?
                WHERE id = ?
                ''',
                (self.nome.value, self.raca.value, self.desc.value, bonus, attr, self.pericia_id),
            )
            conn.commit()

        await interaction.response.send_message(f"✅ Perícia `{self.nome.value}` atualizada.", ephemeral=True)

class SelectEditarPericia(ui.Select):
    def __init__(self, pericias):
        options = [
            discord.SelectOption(
                label=f"{p['id']} - {p['nome']}",
                value=str(p['id']),
                description=f"{p['raca']} | {p['atributo_afetado'] or 'sem bônus'}",
            )
            for p in pericias[:25]
        ]
        super().__init__(placeholder="Escolha a perícia para editar...", options=options)
        self.pericias = {str(p['id']): p for p in pericias}

    async def callback(self, interaction: discord.Interaction):
        pericia = self.pericias[self.values[0]]
        await interaction.response.send_modal(ModalEditarPericia(pericia))


class ModalAdicionarHerancaPericia(ui.Modal, title='Configurar Híbrido'):
    raca_origem = ui.TextInput(label='Raça/Vaga híbrida', placeholder='Ex: Vaizard')
    racas_pericia = ui.TextInput(label='Perícias liberadas', placeholder='Ex: Shinigami, Hollow')

    async def on_submit(self, interaction: discord.Interaction):
        inserted, targets = add_pericia_race_inheritance(self.raca_origem.value, self.racas_pericia.value)
        if not self.raca_origem.value.strip() or not targets:
            return await interaction.response.send_message(
                "❌ Informe a raça híbrida e pelo menos uma raça de perícia.",
                ephemeral=True,
            )

        target_text = ", ".join(targets)
        if inserted == 0:
            return await interaction.response.send_message(
                f"ℹ️ `{self.raca_origem.value.strip()}` já possuía acesso a: `{target_text}`.",
                ephemeral=True,
            )
        await interaction.response.send_message(
            f"✅ `{self.raca_origem.value.strip()}` agora acessa perícias de: `{target_text}`.",
            ephemeral=True,
        )


class ModalRemoverHerancaPericia(ui.Modal, title='Remover Híbrido'):
    raca_origem = ui.TextInput(label='Raça/Vaga híbrida', placeholder='Ex: Vaizard')
    raca_pericia = ui.TextInput(
        label='Raça de perícia (opcional)',
        placeholder='Ex: Hollow. Deixe vazio para remover todas.',
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        removed = remove_pericia_race_inheritance(self.raca_origem.value, self.raca_pericia.value)
        if removed == 0:
            return await interaction.response.send_message("❌ Nenhuma configuração encontrada para remover.", ephemeral=True)

        if self.raca_pericia.value.strip():
            msg = f"✅ Removido acesso de `{self.raca_origem.value.strip()}` às perícias de `{self.raca_pericia.value.strip()}`."
        else:
            msg = f"✅ Removidas `{removed}` configurações de `{self.raca_origem.value.strip()}`."
        await interaction.response.send_message(msg, ephemeral=True)


class AdminPericiaView(ui.View):
    @ui.button(label="Adicionar Perícia", style=discord.ButtonStyle.green)
    async def add(self, interaction, button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar perícias.", ephemeral=True)
        await interaction.response.send_modal(ModalCriarPericia())

    @ui.button(label="Listar Perícias", style=discord.ButtonStyle.secondary)
    async def list(self, interaction, button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar perícias.", ephemeral=True)
        with get_connection() as conn:
            res = conn.execute('SELECT id, nome, raca, bonus_valor, atributo_afetado FROM pericias_base').fetchall()
        
        if not res: return await interaction.response.send_message("Nenhuma perícia cadastrada.", ephemeral=True)
        
        txt = "\n".join([f"ID: `{r[0]}` | **{r[1]}** ({r[2]}) - {_format_admin_bonus(r[3], r[4])}" for r in res])
        await interaction.response.send_message(f"📜 **Perícias do Sistema:**\n{txt}", ephemeral=True)

    @ui.button(label="Editar Perícia", style=discord.ButtonStyle.primary)
    async def edit(self, interaction, button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar perícias.", ephemeral=True)
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            pericias = conn.execute(
                'SELECT id, nome, raca, descricao, bonus_valor, atributo_afetado FROM pericias_base ORDER BY nome COLLATE NOCASE'
            ).fetchall()

        if not pericias:
            return await interaction.response.send_message("Nenhuma perícia cadastrada.", ephemeral=True)

        view = ui.View(timeout=120)
        view.add_item(SelectEditarPericia([dict(p) for p in pericias]))
        await interaction.response.send_message("Escolha qual perícia deseja editar:", view=view, ephemeral=True)

    @ui.button(label="Listar Híbridos", style=discord.ButtonStyle.secondary)
    async def list_hybrids(self, interaction, button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar perícias.", ephemeral=True)

        rows = list_pericia_race_inheritance()
        if not rows:
            return await interaction.response.send_message("Nenhum híbrido configurado.", ephemeral=True)

        grouped = {}
        for row in rows:
            grouped.setdefault(row["raca_origem"], []).append(row["raca_pericia"])

        lines = [f"• **{source}**: {', '.join(targets)}" for source, targets in grouped.items()]
        await interaction.response.send_message("🧬 **Híbridos de Perícia:**\n" + "\n".join(lines), ephemeral=True)

    @ui.button(label="Adicionar Híbrido", style=discord.ButtonStyle.success)
    async def add_hybrid(self, interaction, button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar perícias.", ephemeral=True)
        await interaction.response.send_modal(ModalAdicionarHerancaPericia())

    @ui.button(label="Remover Híbrido", style=discord.ButtonStyle.danger)
    async def remove_hybrid(self, interaction, button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores podem configurar perícias.", ephemeral=True)
        await interaction.response.send_modal(ModalRemoverHerancaPericia())

class PericiaSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="pericia", aliases=["perícia", "pericias", "perícias"], help="Abre o menu de perícias do seu personagem.")
    async def pericia_cmd(self, ctx):
        from cogs.player_system import build_pericia_image_embed

        file, embed, view = build_pericia_image_embed(ctx.author.id, page=0)
        if not embed:
            return await ctx.send("❌ Você não possui um personagem.")
        await ctx.send(file=file, embed=embed, view=view)

    @commands.command(name="config_pericia", aliases=["config_perícia", "config_pericias", "config_perícias"])
    @commands.has_permissions(administrator=True)
    async def config_pericia(self, ctx):
        """Abre o menu administrativo de perícias."""
        await ctx.send("⚙️ **Configuração de Perícias**", view=AdminPericiaView())

    @commands.command(name="limpar_pericia", aliases=["limpar_perícia", "limpar_pericias", "limpar_perícias"], hidden=True)
    @guild_owner_only()
    async def limpar_pericia(self, ctx, pericia_id: int):
        """Remove uma perícia do sistema pelo ID."""
        with get_connection() as conn:
            conn.execute('DELETE FROM pericias_base WHERE id = ?', (pericia_id,))
            conn.execute('DELETE FROM player_pericias WHERE pericia_id = ?', (pericia_id,))
            conn.commit()
        await ctx.send(f"✅ Perícia `{pericia_id}` removida.")

async def setup(bot):
    await bot.add_cog(PericiaSystem(bot))
