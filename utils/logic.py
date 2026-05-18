import datetime
import discord
import logging
import math
import sqlite3
from database import get_connection
from utils.race_restrictions import normalize_race_restriction, race_restriction_allows

logger = logging.getLogger("nemu.logic")

POTENCIAL_ATTRIBUTES = ("forca", "velocidade", "resistencia")
POTENCIAL_ATTRIBUTE_LABELS = {
    "forca": "Força",
    "velocidade": "Velocidade",
    "resistencia": "Resistência",
}
POTENCIAL_ATTRIBUTE_ALIASES = {
    "forca": "forca",
    "força": "forca",
    "f": "forca",
    "velocidade": "velocidade",
    "vel": "velocidade",
    "v": "velocidade",
    "resistencia": "resistencia",
    "resistência": "resistencia",
    "res": "resistencia",
    "r": "resistencia",
}
RACE_CATEGORIES = ("Raças Iniciais", "Raças Normais", "Raças Especiais")

SPIRITUAL_POWER_LEVELS = [
    ("Básico", 1_000, 25_000),
    ("Comum", 25_001, 75_000),
    ("Médio", 75_001, 150_000),
    ("Elevado", 150_001, 300_000),
    ("Alto", 300_001, 600_000),
    ("Superior", 600_001, 1_000_000),
    ("Grande", 1_000_001, 2_500_000),
    ("Imponente", 2_500_001, 5_000_000),
    ("Massivo", 5_000_001, 10_000_000),
    ("Colossal", 10_000_001, 20_000_000),
    ("Avassalador", 20_000_001, 40_000_000),
    ("Monstruoso", 40_000_001, 75_000_000),
    ("Imenso", 75_000_001, 120_000_000),
    ("Abissal", 120_000_001, 200_000_000),
    ("Lendário", 200_000_001, 350_000_000),
    ("Catastrófico", 350_000_001, 500_000_000),
    ("Divino", 500_000_001, 750_000_000),
    ("Transcendental", 750_000_001, 1_000_000_000),
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
    h_abrir = config[1]
    h_fechar = config[2]
    dias_str = config[3]
    if not h_abrir or not h_fechar or not dias_str:
        return False
    agora = datetime.datetime.now()
    hora_atual = agora.strftime("%H:%M")
    dia_atual = str(agora.weekday())
    dias_ativos = [dia.strip() for dia in str(dias_str).split(",") if dia.strip()]
    return (dia_atual in dias_ativos) and (h_abrir <= hora_atual < h_fechar)


def normalize_potencial_attribute(value):
    text = str(value or "").strip().lower()
    return POTENCIAL_ATTRIBUTE_ALIASES.get(text)


def _positive_multiplier(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def get_potencial_effects(user_id):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        pots = conn.execute(
            """
            SELECT pp.potencial, pp.ativo, pp.mult_override,
                   pp.mult_forca AS player_mult_forca,
                   pp.mult_velocidade AS player_mult_velocidade,
                   pp.mult_resistencia AS player_mult_resistencia,
                   p.multiplicador,
                   p.mult_forca AS base_mult_forca,
                   p.mult_velocidade AS base_mult_velocidade,
                   p.mult_resistencia AS base_mult_resistencia
            FROM player_potencial pp
            JOIN potenciais p ON pp.potencial = p.nome
            WHERE pp.user_id = ?
            """,
            (user_id,),
        ).fetchall()

    multipliers = {attr: 1.0 for attr in POTENCIAL_ATTRIBUTES}
    source_names = {attr: [] for attr in POTENCIAL_ATTRIBUTES}
    active_names = []
    active = False

    for pot in pots:
        if pot["ativo"] != 1:
            continue

        active = True
        active_names.append(pot["potencial"])
        base_general = _positive_multiplier(pot["multiplicador"]) or 1.0
        player_general = _positive_multiplier(pot["mult_override"])

        for attr in POTENCIAL_ATTRIBUTES:
            player_attr = _positive_multiplier(pot[f"player_mult_{attr}"])
            base_attr = _positive_multiplier(pot[f"base_mult_{attr}"])
            eff_mult = player_attr or player_general or base_attr or base_general
            multipliers[attr] *= eff_mult
            source_names[attr].append(pot["potencial"])

    return {
        "multipliers": multipliers,
        "names": " + ".join(active_names),
        "source_names": {attr: " + ".join(names) for attr, names in source_names.items()},
        "active": active,
    }


def get_potencial_info(user_id, atributo=None):
    effects = get_potencial_effects(user_id)
    attr = normalize_potencial_attribute(atributo) if atributo else None
    if attr:
        return effects["multipliers"][attr], effects["source_names"].get(attr, ""), effects["active"]

    values = list(effects["multipliers"].values())
    total_mult = values[0] if values and all(value == values[0] for value in values) else max(values or [1.0])
    return total_mult, effects["names"], effects["active"]


def _effective_vaga_restriction(categoria, restricao):
    if categoria == "Zanpakuto":
        return "Shinigami"
    return normalize_race_restriction(restricao)


def _player_race_sources(cursor, user_id, base_raca):
    sources = [base_raca]
    rows = cursor.execute(
        '''
        SELECT pv.vaga_nome
        FROM player_vagas pv
        JOIN vagas v ON pv.vaga_nome = v.nome
        WHERE pv.user_id = ?
          AND v.categoria IN ("Raças Iniciais", "Raças Normais", "Raças Especiais")
        ''',
        (user_id,),
    ).fetchall()
    sources.extend(row[0] for row in rows if row and row[0])
    return sources

async def atribuir_vaga_logica(guild, membro, nome_vaga):
    with get_connection() as conn:
        cursor = conn.cursor()
        char = cursor.execute('SELECT 1 FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
        if not char: return False, "❌ Usuário não possui personagem."

        res = cursor.execute('SELECT role_id, limite, restricao_raca, categoria FROM vagas WHERE nome = ?', (nome_vaga,)).fetchone()
        if not res: return False, f"❌ Vaga `{nome_vaga}` não existe."

        role_id, limite, restricao, categoria = res

        restricao = _effective_vaga_restriction(categoria, restricao)
        if restricao and restricao.lower() != "nenhuma" and restricao.lower() != "todos":
            p_raca = cursor.execute('SELECT raca FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
            race_sources = _player_race_sources(cursor, membro.id, p_raca[0] if p_raca else None)
            if not p_raca or not race_restriction_allows(restricao, race_sources):
                return False, f"❌ Restrito a: {restricao}."

        if categoria in RACE_CATEGORIES:
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
