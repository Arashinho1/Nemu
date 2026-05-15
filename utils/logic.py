import datetime
import discord
import logging
import math
import sqlite3
from database import get_connection

logger = logging.getLogger("nemu.logic")

SPIRITUAL_POWER_LEVELS = [
    ("Básico", 1_000, 100_000),
    ("Médio", 100_001, 1_000_000),
    ("Alto", 1_000_001, 10_000_000),
    ("Grande", 10_000_001, 100_000_000),
    ("Imenso", 100_000_001, 1_000_000_000),
    ("Imensurável", 1_000_000_001, float("inf")),
]

REIATSU_LEVELS = SPIRITUAL_POWER_LEVELS
REIATSU_LIMITS = [(nome, maximo) for nome, _, maximo in SPIRITUAL_POWER_LEVELS]


def normalize_reiatsu_limit_index(limite_index):
    try:
        idx = int(limite_index or 0)
    except (TypeError, ValueError):
        idx = 0
    return max(0, min(idx, len(SPIRITUAL_POWER_LEVELS) - 1))


def reiatsu_cap_for_limit_index(limite_index):
    idx = normalize_reiatsu_limit_index(limite_index)
    return SPIRITUAL_POWER_LEVELS[idx][2]


def reiatsu_floor_for_limit_index(limite_index):
    idx = normalize_reiatsu_limit_index(limite_index)
    return SPIRITUAL_POWER_LEVELS[idx][1]


def format_reiatsu_limit(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isinf(number):
        return "∞"
    return f"{int(number):,}".replace(",", ".")


def calcular_reiryoku(f, v, r):
    return f + v + r

def calcular_reiatsu(reiryoku, multiplicador):
    return int(reiryoku * multiplicador)

def calcular_reiatsu_maxima(reiryoku_max, multiplicador):
    return calcular_reiatsu(max(0, int(reiryoku_max or 0)), multiplicador)

def calcular_reiatsu_efetiva(reiryoku_atual, reiryoku_max, multiplicador):
    reiryoku_max = max(0, int(reiryoku_max or 0))
    reiryoku_atual = max(0, min(int(reiryoku_atual or 0), reiryoku_max))
    if reiryoku_max <= 0 or reiryoku_atual <= 0:
        return 0
    reiatsu_max = calcular_reiatsu_maxima(reiryoku_max, multiplicador)
    return int(reiatsu_max * (reiryoku_atual / reiryoku_max))

def nivel_reiatsu(valor, limite_index):
    limite_index = normalize_reiatsu_limit_index(limite_index)

    atual_idx = 0
    for i, (_, minimo, maximo) in enumerate(SPIRITUAL_POWER_LEVELS):
        if valor <= maximo and (valor >= minimo or i == 0):
            atual_idx = i
            break
        atual_idx = len(SPIRITUAL_POWER_LEVELS) - 1

    if atual_idx > limite_index:
        return f"{SPIRITUAL_POWER_LEVELS[limite_index][0]}: Grau Alto ⚠️ (Limit Break Necessário)"

    nome, minimo, maximo = SPIRITUAL_POWER_LEVELS[atual_idx]
    if math.isinf(float(maximo)):
        return f"{nome}: Grau Alto"

    faixa = maximo - minimo
    percentual = 0 if faixa <= 0 else ((max(valor, minimo) - minimo) / faixa) * 100
    grau = "Grau Baixo" if percentual <= 33.3 else "Grau Médio" if percentual <= 66.6 else "Grau Alto"
    return f"{nome}: {grau}"

def esta_na_janela_pretensao(config):
    if not config or not config[0]: return False
    canal_id, h_abrir, h_fechar, dias_str = config
    agora = datetime.datetime.now()
    hora_atual = agora.strftime("%H:%M")
    dia_atual = str(agora.weekday())
    return (dia_atual in dias_str.split(",")) and (h_abrir <= hora_atual < h_fechar)

def get_potencial_info(user_id):
    with get_connection() as conn:
        pots = conn.execute('SELECT potencial, ativo, mult_override FROM player_potencial WHERE user_id = ?', (user_id,)).fetchall()
        total_mult = 1.0
        nomes_ativos = []
        ativo = False
        for nome, ativo_flag, m_override in pots:
            base = conn.execute('SELECT multiplicador FROM potenciais WHERE nome = ?', (nome,)).fetchone()
            if base and ativo_flag == 1:
                eff_mult = m_override if m_override and m_override > 0 else base[0]
                total_mult *= eff_mult
                nomes_ativos.append(nome)
                ativo = True
        return total_mult, " + ".join(nomes_ativos), ativo

async def atribuir_vaga_logica(guild, membro, nome_vaga):
    with get_connection() as conn:
        cursor = conn.cursor()
        char = cursor.execute('SELECT 1 FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
        if not char: return False, "❌ Usuário não possui personagem."

        res = cursor.execute('SELECT role_id, limite, restricao_raca, categoria FROM vagas WHERE nome = ?', (nome_vaga,)).fetchone()
        if not res: return False, f"❌ Vaga `{nome_vaga}` não existe."

        role_id, limite, restricao, categoria = res

        if categoria in ["Raças Iniciais", "Raças Normais", "Raças Especiais"]:
            racas_antigas = cursor.execute('''
                SELECT pv.vaga_nome, v.role_id FROM player_vagas pv
                JOIN vagas v ON pv.vaga_nome = v.nome
                WHERE pv.user_id = ? AND v.categoria IN ("Raças Normais", "Raças Especiais")
            ''', (membro.id,)).fetchall()
            for r_nome, r_role in racas_antigas:
                if r_role:
                    role_old = guild.get_role(r_role)
                    if role_old: await membro.remove_roles(role_old)
                cursor.execute('DELETE FROM player_vagas WHERE user_id = ? AND vaga_nome = ?', (membro.id, r_nome))
            cursor.execute('UPDATE personagens SET raca = ? WHERE user_id = ?', (nome_vaga, membro.id))

        if restricao and restricao.lower() != "nenhuma":
            p_raca = cursor.execute('SELECT raca FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
            if not p_raca or p_raca[0].lower() != restricao.lower():
                return False, f"❌ Restrito a: {restricao}."

        if limite > 0:
            atual = cursor.execute('SELECT COUNT(*) FROM player_vagas WHERE vaga_nome = ?', (nome_vaga,)).fetchone()[0]
            if atual >= limite:
                if not cursor.execute('SELECT 1 FROM player_vagas WHERE user_id = ? AND vaga_nome = ?', (membro.id, nome_vaga)).fetchone():
                    return False, f"❌ Vaga lotada ({atual}/{limite})."

        if cursor.execute('SELECT 1 FROM player_vagas WHERE user_id = ? AND vaga_nome = ?', (membro.id, nome_vaga)).fetchone():
            return True, "✅ Já possui."

        cursor.execute('INSERT INTO player_vagas (user_id, vaga_nome) VALUES (?, ?)', (membro.id, nome_vaga))
        
        if role_id:
            role = guild.get_role(role_id)
            if role:
                try:
                    await membro.add_roles(role)
                except discord.DiscordException:
                    logger.warning("Falha ao adicionar cargo %s ao membro %s.", role_id, membro.id)

        filhas = [row[0] for row in cursor.execute('SELECT vaga_filha FROM vagas_vinculo WHERE vaga_pai = ?', (nome_vaga,)).fetchall()]
        conn.commit()

    for filha in filhas:
        await atribuir_vaga_logica(guild, membro, filha)
    return True, "✅ Sucesso"
