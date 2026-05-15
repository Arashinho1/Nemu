import discord
from discord.ext import commands
from discord import ui
from utils.ui_components import PaginatorView

class CommandSelect(ui.Select):
    def __init__(self, categories, is_admin=False):
        options = [discord.SelectOption(label=cat, value=cat) for cat in categories.keys()]
        super().__init__(placeholder="Escolha uma categoria para filtrar...", options=options)
        self.categories = categories
        self.is_admin = is_admin

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        cmds = self.categories[cat]
        
        embeds = []
        title = f"📂 Comandos: {cat}" + (" (Staff)" if self.is_admin else "")
        current_embed = discord.Embed(title=title, color=0x2ecc71 if not self.is_admin else 0xe74c3c)
        
        for name, desc in cmds.items():
            if len(current_embed.fields) == 10:
                embeds.append(current_embed)
                current_embed = discord.Embed(title=title + " (Cont.)", color=current_embed.color)
            current_embed.add_field(name=f".{name}", value=desc, inline=False)
        
        embeds.append(current_embed)

        if len(embeds) > 1:
            view = PaginatorView(embeds)
            view.add_item(CommandSelect(self.categories, self.is_admin))
            await interaction.response.edit_message(embed=embeds[0], view=view)
        else:
            view = ui.View()
            view.add_item(CommandSelect(self.categories, self.is_admin))
            await interaction.response.edit_message(embed=embeds[0], view=view)

class PlayerGuideView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="🏠 Início", style=discord.ButtonStyle.primary)
    async def home(self, interaction, button):
        embed = discord.Embed(title="📖 Guia do Recruta", color=0x3498db)
        embed.description = (
            "Bem-vindo ao RPG! Para começar sua jornada:\n\n"
            "1. Use `.criar` para escolher sua raça inicial.\n"
            "2. Complete seu registro seguindo as instruções do bot.\n"
            "3. Use `.perfil` para ver seus dados iniciais."
        )
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="⚔️ Atributos", style=discord.ButtonStyle.secondary)
    async def attrs(self, interaction, button):
        embed = discord.Embed(title="⚔️ Entendendo Atributos", color=0xe74c3c)
        embed.description = (
            "**Cálculo de Pontos:**\nCada 1 ponto investido aumenta em +1 seu atributo base.\n\n"
            "**Impacto na Reiatsu:**\nSua Reiatsu é o resultado de: `(Soma dos Atributos Base + Bônus Fixos) * Multiplicadores`.\n\n"
            "• **Força:** Dano físico e potência de impacto.\n"
            "• **Velocidade:** Ordem de ataque e capacidade de esquiva.\n"
            "• **Resistência:** Vida, mitigação de dano e fôlego espiritual."
        )
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="💠 Reiatsu", style=discord.ButtonStyle.secondary)
    async def energy(self, interaction, button):
        embed = discord.Embed(title="💠 Energia Espiritual", color=0x9b59b6)
        embed.description = (
            "**Reiryoku:** É a sua reserva total de energia.\n"
            "**Reiatsu:** É a pressão que você exerce no ambiente.\n\n"
            "Seu nível de Reiatsu (Comum, Incomum, etc.) define sua força perante outros seres. "
            "Ao atingir o limite de um nível, você precisará de um **Limit Break** com a Staff."
        )
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="🔥 Liberações", style=discord.ButtonStyle.secondary)
    async def potentials(self, interaction, button):
        embed = discord.Embed(title="🔥 Potenciais e Liberações", color=0xe67e22)
        embed.description = (
            "**Potenciais:** São suas transformações (Shikai, Bankai, Resurrección).\n"
            "• Use `.potencial` para gerenciar os seus.\n"
            "• No menu `.potencial`, use **Configurar Imagem** para definir seu GIF/imagem pessoal.\n"
            "• Use `.p Shikai` ou `.liberar_potencial Shikai` para ativar/desativar um potencial já atribuído.\n"
            "• **Liberação:** Ao liberar, seus atributos recebem um multiplicador massivo por tempo limitado.\n"
            "• Após o uso, o potencial entra em *Cooldown* (tempo de recarga)."
        )
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="📜 Comandos", style=discord.ButtonStyle.secondary)
    async def commands_list(self, interaction, button):
        embed = discord.Embed(title="📜 Comandos Úteis", color=0x2ecc71)
        embed.add_field(name="Informação", value="`.perfil`, `.pericia`, `.kido`, `.tecnica`, `.vagas`, `.info ID`, `.buffs`, `.comandos`", inline=False)
        embed.add_field(name="Ação", value="`.criar`, `.deletar`, `.potencial`, `.p Shikai`, `.kido usar`, `.tecnica usar`, `.passar_turno`, `.pretensão`", inline=False)
        await interaction.response.edit_message(embed=embed)

class AdminGuideView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="⚙️ Inicial", style=discord.ButtonStyle.primary)
    async def setup_guide(self, interaction, button):
        embed = discord.Embed(title="⚙️ Guia de Configuração", color=0x7f8c8d)
        embed.description = (
            "Como configurar o bot em um novo servidor:\n\n"
            "1. `.restringir_bot`: Bloqueia comandos do bot em canais específicos.\n"
            "2. `.setar_logs`: Canal para monitorar comandos.\n"
            "3. `.inicial config`: Gerencie as raças que aparecerão no `.criar`."
        )
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="🎭 Vagas", style=discord.ButtonStyle.secondary)
    async def vagas_guide(self, interaction, button):
        embed = discord.Embed(title="🎭 Gestão de Vagas", color=0xf1c40f)
        embed.description = (
            "Vagas são bônus que dão cargos e multiplicadores.\n\n"
            "• Use `.vagas` para listar vagas e, como admin, criar novas vagas pelo botão.\n"
            "• Use `.info ID` para consultar uma vaga.\n"
            "• Use `.buffar` para configurar bônus matemáticos."
        )
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="✨ Passivas", style=discord.ButtonStyle.secondary)
    async def skills_guide(self, interaction, button):
        embed = discord.Embed(title="✨ Gestão de Perícias", color=0x1abc9c)
        embed.description = (
            "1. `.config_pericia`: Abre o painel administrativo de perícias.\n"
            "2. Jogadores usam `.pericia` ou o botão `Perícias` dentro do `.perfil`.\n"
            "3. Apenas o dono do servidor pode usar `.limpar_pericia ID` para remover uma perícia cadastrada."
        )
        await interaction.response.edit_message(embed=embed)

    @ui.button(label="🆘 Ajuda", style=discord.ButtonStyle.danger)
    async def help_shortcut(self, interaction, button):
        await interaction.response.send_message("Use `.guia`, `.comandos`, `.guia_adm` ou `.comandos_adm`.", ephemeral=True)

class GuideSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="guia")
    async def player_guide(self, ctx):
        """Mostra o guia interativo para jogadores."""
        embed = discord.Embed(
            title="⛩️ Central de Ajuda - Nemu Bot",
            description="Bem-vindo ao Guia Interativo. Utilize os botões abaixo para navegar pelos tópicos.",
            color=0x3498db
        )
        await ctx.send(embed=embed, view=PlayerGuideView())

    @commands.command(name="guia_adm")
    @commands.has_permissions(administrator=True)
    async def admin_guide(self, ctx):
        """Mostra o guia interativo para administradores."""
        embed = discord.Embed(
            title="🛠️ Painel de Instruções Administrativas",
            description="Central de ajuda para moderadores e administradores do RPG.",
            color=0x7f8c8d
        )
        await ctx.send(embed=embed, view=AdminGuideView())

    @commands.command(name="comandos")
    async def player_commands(self, ctx):
        """Lista todos os comandos disponíveis para jogadores."""
        data = {
            "Geral": {
                "criar": "Inicia a criação do seu personagem.",
                "deletar": "Apaga sua própria ficha permanentemente após confirmação.",
                "perfil": "Mostra sua ficha em imagem com atributos, distribuição e botão de perícias.",
                "buffs": "Lista seus bônus ativos e multiplicadores finais.",
                "guia": "Abre o guia interativo de sistemas.",
                "comandos": "Abre esta lista de comandos."
            },
            "Progressão": {
                "pericia": "Abre a tela de perícias/passivas do seu personagem.",
                "potencial": "Gerencia suas liberações, lista seus potenciais e configura imagem/GIF.",
                "p": "Ativa ou desativa um potencial. Uso: `.p Shikai` ou `.liberar_potencial Shikai`.",
                "passar_turno": "Avança seu turno e reduz cooldowns/durações de Kidō, técnicas e potenciais."
            },
            "Kidō": {
                "kido": "Abre sua biblioteca de Kidō para Shinigami e Vaizard, com status, listas conhecidas e pedido de descanso.",
                "kido_usar": "Abre o menu para conjurar Kidō por classificação disponível.",
                "kido_criar": "Abre o menu de criação com categoria técnica e classificação Comum/Exclusivo/Proibido.",
                "info_kido": "Mostra detalhes de Kidō oficiais, exclusivos e proibidos.",
                "listar_kido": "Abre a listagem de Kidō oficiais, criados, exclusivos e proibidos.",
                "kido_usar": "Conjura Kidō com Encantamento, Sem Encantamento ou Nijū Eishō no Tier III.",
                "kido_criar": "Cria Kidō próprios como Comum, Exclusivo ou Proibido; administradores também registram Kidō do sistema.",
                "kido simular": "Calcula gasto, poder e cooldown sem consumir Reiryoku.",
                "kido_simular": "Atalho para simulação de Kidō por número.",
                "kido descansar": "Pede descanso para restaurar o Reiryoku reservado para Kidō."
            },
            "Técnicas": {
                "tecnica": "Abre o menu de técnicas oficiais e criadas.",
                "tecnica_usar": "Usa uma técnica disponível para aplicar buff físico temporário.",
                "tecnica_criar": "Cria uma técnica sem buff; a staff configura os bônus em `.buffar`.",
                "listar_tecnicas": "Lista técnicas oficiais e criadas."
            },
            "Vagas": {
                "vagas": "Lista cargos, títulos e linhagens.",
                "info": "Mostra detalhes técnicos de uma vaga pelo ID."
            },
            "Sistemas": {
                "pretensão": "Verifica o status do resgate de IDs."
            }
        }
        
        embed = discord.Embed(title="⌨️ Lista de Comandos", description="Selecione uma categoria abaixo para filtrar os comandos disponíveis.", color=0x2ecc71)
        view = ui.View()
        view.add_item(CommandSelect(data))
        await ctx.send(embed=embed, view=view)

    @commands.command(name="comandos_adm")
    @commands.has_permissions(administrator=True)
    async def admin_commands(self, ctx):
        """Lista todos os comandos administrativos da Staff."""
        data = {
            "Configuração": {
                "setar_logs": "Define o canal de logs do bot.",
                "restringir_bot": "Bloqueia comandos do bot no canal atual ou em um canal informado.",
                "setar_bot": "Alias ativo de `.restringir_bot`.",
                "liberar_bot": "Libera comandos do bot no canal atual ou em um canal informado.",
                "bloqueios_bot": "Lista os canais onde o bot está bloqueado.",
                "comandos_adm": "Abre esta lista administrativa."
            },
            "Atribuição (Setar)": {
                "setar_potencial": "Atribui uma liberação (Shikai/Bankai) a um jogador.",
                "ajustar_potencial": "Ajusta multiplicador, duração ou cooldown individual. Uso: `.ajustar_potencial @membro \"Shikai\" mult 3.0`.",
                "restaura_cd": "Zera cooldowns ativos de Kidō, técnicas e potenciais de um jogador.",
                "listar_potenciais": "Mostra uma lista técnica de todos os potenciais criados."
            },
            "Recursos & Pontos": {
                "dar": "Dá pontos para um jogador. Uso: `.dar <pa|pp> @membro valor`.",
                "resetar": "Reseta a ficha e progresso de um jogador. Uso: `.resetar @membro`.",
                "setar_nivel": "Define o patamar de Reiatsu de um jogador.",
                "romper_limite": "Sobe 1 limite. Use `.romper_limite completo @membro` para sincronizar com a Reiatsu atual.",
                "romper_limite_completo": "Atalho para ajustar o limite diretamente ao nível da Reiatsu atual.",
                "dar_slot_potencial": "Aumenta o limite de transformações."
            },
            "Criação de Conteúdo": {
                "vagas": "Menu interativo para listar vagas e criar vagas/cargos via botão admin.",
                "buffar": "Configura buffs por categoria de vaga, buffs de técnica e consumo de potencial.",
                "inicial config": "Gerencia as raças iniciais do menu .criar.",
                "config_pericia": "Painel administrativo para adicionar/listar perícias.",
                "potencial": "Menu de potenciais; administradores recebem botões de criar/editar.",
                "kido": "Menu de Kidō; `.kido_criar` permite classificar criações e registros oficiais.",
                "tecnica": "Menu de técnicas; `.tecnica_criar` registra criações e técnicas oficiais."
            },
            "Dono do Servidor": {
                "reload": "Recarrega módulos ou reinicia o bot.",
                "apagar_servidor": "Reset TOTAL do banco de dados (Wipe de sistema).",
                "resetar_servidor": "Reseta apenas as fichas e progresso dos jogadores.",
                "limpar_pericia": "Remove uma perícia do sistema pelo ID.",
                "remover_potencial": "Remove uma liberação/potencial de um jogador.",
                "remover_slot_potencial": "Diminui o limite de transformações."
            },
            "Auxílio": {
                "guia_adm": "Abre o guia interativo para moderadores."
            }
        }
        
        embed = discord.Embed(title="🛠️ Comandos Administrativos", description="Acesso restrito à Staff. Selecione um filtro abaixo.", color=0xe74c3c)
        view = ui.View()
        view.add_item(CommandSelect(data, is_admin=True))
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(GuideSystem(bot))
