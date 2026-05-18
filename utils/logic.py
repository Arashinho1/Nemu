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
    ("Básico", 1_000, 5_000),
    ("Iniciante", 5_001, 50_000),
    ("Amador", 50_001, 300_000),
    ("Desenvolvido", 300_001, 1_000_000),
    ("Alto", 1_000_001, 1_500_000),
    ("Elite", 1_500_001, 3_000_000),
    ("Anormal", 3_000_001, 10_000_000),
    ("Grande", 10_000_001, 30_000_000),
    ("Imenso", 30_000_001, 150_000_000),
    ("Imensurável", 150_000_001, 500_000_000),
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


def _pericia_level_cost(nivel_atual):
    if nivel_atual >= 6:
        return None
    return int(100 * (1.5 ** (nivel_atual - 1)))


def _pericia_total_invested(nivel, pp_investido):
    total = int(pp_investido or 0)
    for level in range(1, int(nivel or 1)):
        total += _pericia_level_cost(level) or 0
    return total


def _pericia_state_from_total(total):
    total = max(0, int(total or 0))
    nivel = 1
    while nivel < 6:
        custo = _pericia_level_cost(nivel)
        if custo is None or total < custo:
            break
        total -= custo
        nivel += 1
    return nivel, total


def _remove_pa_from_character(cursor, user_id, amount):
    remaining = max(0, int(amount or 0))
    if remaining <= 0:
        return 0

    row = cursor.execute(
        'SELECT pontos_livres, forca, velocidade, resistencia FROM personagens WHERE user_id = ?',
        (user_id,),
    ).fetchone()
    if not row:
        return 0

    pontos_livres, forca, velocidade, resistencia = [int(value or 0) for value in row]
    from_pool = min(pontos_livres, remaining)
    pontos_livres -= from_pool
    remaining -= from_pool

    attrs = {"forca": forca, "velocidade": velocidade, "resistencia": resistencia}
    for attr, value in sorted(attrs.items(), key=lambda item: item[1], reverse=True):
        if remaining <= 0:
            break
        taken = min(value, remaining)
        attrs[attr] -= taken
        remaining -= taken

    removed = int(amount or 0) - remaining
    cursor.execute(
        '''
        UPDATE personagens
        SET pontos_livres = ?, forca = ?, velocidade = ?, resistencia = ?
        WHERE user_id = ?
        ''',
        (pontos_livres, attrs["forca"], attrs["velocidade"], attrs["resistencia"], user_id),
    )
    return removed


def _remove_pp_from_character(cursor, user_id, amount):
    remaining = max(0, int(amount or 0))
    if remaining <= 0:
        return 0

    row = cursor.execute('SELECT pontos_pericia FROM personagens WHERE user_id = ?', (user_id,)).fetchone()
    if not row:
        return 0

    pontos_pericia = int(row[0] or 0)
    from_pool = min(pontos_pericia, remaining)
    pontos_pericia -= from_pool
    remaining -= from_pool
    cursor.execute('UPDATE personagens SET pontos_pericia = ? WHERE user_id = ?', (pontos_pericia, user_id))

    pericias = []
    for pericia_id, nivel, pp_investido in cursor.execute(
        'SELECT pericia_id, nivel, pp_investido FROM player_pericias WHERE user_id = ?',
        (user_id,),
    ).fetchall():
        total = _pericia_total_invested(nivel, pp_investido)
        if total > 0:
            pericias.append((pericia_id, total))

    for pericia_id, total in sorted(pericias, key=lambda item: item[1], reverse=True):
        if remaining <= 0:
            break
        taken = min(total, remaining)
        new_total = total - taken
        remaining -= taken
        if new_total <= 0:
            cursor.execute(
                'DELETE FROM player_pericias WHERE user_id = ? AND pericia_id = ?',
                (user_id, pericia_id),
            )
            continue
        new_level, new_invested = _pericia_state_from_total(new_total)
        cursor.execute(
            '''
            UPDATE player_pericias
            SET nivel = ?, pp_investido = ?
            WHERE user_id = ? AND pericia_id = ?
            ''',
            (new_level, new_invested, user_id, pericia_id),
        )

    return int(amount or 0) - remaining


def _grant_vaga_points(cursor, user_id, nome_vaga, categoria, pa_bonus, pp_bonus, pa_inicial, pp_inicial):
    pontos_pa = int(pa_inicial or 0) if categoria == "Raças Iniciais" else int(pa_bonus or 0)
    pontos_pp = int(pp_inicial or 0) if categoria == "Raças Iniciais" else int(pp_bonus or 0)
    if not pontos_pa and not pontos_pp:
        return 0, 0

    cursor.execute(
        '''
        UPDATE personagens
        SET pontos_livres = pontos_livres + ?,
            pontos_pericia = pontos_pericia + ?
        WHERE user_id = ?
        ''',
        (pontos_pa, pontos_pp, user_id),
    )
    if categoria != "Raças Iniciais":
        cursor.execute(
            '''
            INSERT OR REPLACE INTO player_vaga_pontos (user_id, vaga_nome, pontos_pa, pontos_pp)
            VALUES (?, ?, ?, ?)
            ''',
            (user_id, nome_vaga, pontos_pa, pontos_pp),
        )
    return pontos_pa, pontos_pp


def _revoke_vaga_points(cursor, user_id, nome_vaga, categoria):
    if categoria == "Raças Iniciais":
        return 0, 0

    row = cursor.execute(
        '''
        SELECT pontos_pa, pontos_pp
        FROM player_vaga_pontos
        WHERE user_id = ? AND vaga_nome = ?
        ''',
        (user_id, nome_vaga),
    ).fetchone()
    if not row:
        return 0, 0

    pontos_pa, pontos_pp = int(row[0] or 0), int(row[1] or 0)
    removed_pa = _remove_pa_from_character(cursor, user_id, pontos_pa)
    removed_pp = _remove_pp_from_character(cursor, user_id, pontos_pp)
    cursor.execute(
        'DELETE FROM player_vaga_pontos WHERE user_id = ? AND vaga_nome = ?',
        (user_id, nome_vaga),
    )
    return removed_pa, removed_pp


def _sync_race_after_vaga_removal(cursor, user_id, removed_vaga):
    current = cursor.execute('SELECT raca FROM personagens WHERE user_id = ?', (user_id,)).fetchone()
    if not current or current[0] != removed_vaga:
        return

    fallback = cursor.execute(
        '''
        SELECT pv.vaga_nome
        FROM player_vagas pv
        JOIN vagas v ON pv.vaga_nome = v.nome
        WHERE pv.user_id = ?
          AND v.categoria IN ("Raças Especiais", "Raças Normais", "Raças Iniciais")
          AND COALESCE(pv.extra, 0) = 0
        ORDER BY CASE v.categoria
            WHEN "Raças Especiais" THEN 0
            WHEN "Raças Normais" THEN 1
            ELSE 2
        END
        LIMIT 1
        ''',
        (user_id,),
    ).fetchone()
    cursor.execute('UPDATE personagens SET raca = ? WHERE user_id = ?', (fallback[0] if fallback else None, user_id))


def _member_has_other_role_source(cursor, user_id, nome_vaga, role_id):
    if not role_id:
        return False
    return cursor.execute(
        '''
        SELECT 1
        FROM player_vagas pv
        JOIN vagas v ON pv.vaga_nome = v.nome
        WHERE pv.user_id = ?
          AND pv.vaga_nome != ?
          AND v.role_id = ?
        LIMIT 1
        ''',
        (user_id, nome_vaga, role_id),
    ).fetchone() is not None


async def _remove_vaga_from_member(cursor, guild, membro, nome_vaga, allow_initial=False, origem_vaga=None):
    vaga = cursor.execute(
        'SELECT role_id, categoria FROM vagas WHERE nome = ?',
        (nome_vaga,),
    ).fetchone()
    if not vaga:
        return False, f"❌ Vaga `{nome_vaga}` não existe.", []

    role_id, categoria = vaga
    if categoria == "Raças Iniciais" and not allow_initial:
        return False, "❌ Raças iniciais não são removidas por esse comando.", []

    if origem_vaga is None:
        assigned = cursor.execute(
            'SELECT 1 FROM player_vagas WHERE user_id = ? AND vaga_nome = ?',
            (membro.id, nome_vaga),
        ).fetchone()
    else:
        assigned = cursor.execute(
            '''
            SELECT 1
            FROM player_vagas
            WHERE user_id = ?
              AND vaga_nome = ?
              AND origem_vaga = ?
            ''',
            (membro.id, nome_vaga, origem_vaga),
        ).fetchone()
    if not assigned:
        return False, f"❌ {membro.mention} não possui `{nome_vaga}`.", []

    removed = []
    filhas = [
        row[0] for row in cursor.execute(
            '''
            SELECT vv.vaga_filha
            FROM vagas_vinculo vv
            JOIN player_vagas pv ON pv.vaga_nome = vv.vaga_filha
            WHERE vv.vaga_pai = ?
              AND pv.user_id = ?
              AND pv.origem_vaga = ?
            ''',
            (nome_vaga, membro.id, nome_vaga),
        ).fetchall()
    ]
    for filha in filhas:
        _, _, child_removed = await _remove_vaga_from_member(
            cursor,
            guild,
            membro,
            filha,
            allow_initial=False,
            origem_vaga=nome_vaga,
        )
        removed.extend(child_removed)

    if role_id and not _member_has_other_role_source(cursor, membro.id, nome_vaga, role_id):
        role = guild.get_role(role_id)
        if role:
            try:
                await membro.remove_roles(role)
            except discord.DiscordException:
                logger.warning("Falha ao remover cargo %s do membro %s.", role_id, membro.id)

    pa_removed, pp_removed = _revoke_vaga_points(cursor, membro.id, nome_vaga, categoria)
    if origem_vaga is None:
        cursor.execute(
            'DELETE FROM player_vagas WHERE user_id = ? AND vaga_nome = ?',
            (membro.id, nome_vaga),
        )
    else:
        cursor.execute(
            '''
            DELETE FROM player_vagas
            WHERE user_id = ?
              AND vaga_nome = ?
              AND origem_vaga = ?
            ''',
            (membro.id, nome_vaga, origem_vaga),
        )
    if categoria in RACE_CATEGORIES:
        _sync_race_after_vaga_removal(cursor, membro.id, nome_vaga)

    removed.append({
        "nome": nome_vaga,
        "categoria": categoria,
        "pontos_pa": pa_removed,
        "pontos_pp": pp_removed,
    })
    return True, "✅ Removida.", removed


async def atribuir_vaga_logica(guild, membro, nome_vaga, extra=False, origem_vaga=None):
    extra = bool(extra)
    with get_connection() as conn:
        cursor = conn.cursor()
        char = cursor.execute('SELECT 1 FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
        if not char: return False, "❌ Usuário não possui personagem."

        res = cursor.execute('''
            SELECT role_id, limite, restricao_raca, categoria,
                   pontos_pa_bonus, pontos_pp_bonus, pontos_pa_inicial, pontos_pp_inicial
            FROM vagas
            WHERE nome = ?
        ''', (nome_vaga,)).fetchone()
        if not res: return False, f"❌ Vaga `{nome_vaga}` não existe."

        role_id, limite, restricao, categoria, pa_bonus, pp_bonus, pa_inicial, pp_inicial = res

        restricao = _effective_vaga_restriction(categoria, restricao)
        if restricao and restricao.lower() != "nenhuma" and restricao.lower() != "todos":
            p_raca = cursor.execute('SELECT raca FROM personagens WHERE user_id = ?', (membro.id,)).fetchone()
            race_sources = _player_race_sources(cursor, membro.id, p_raca[0] if p_raca else None)
            if not p_raca or not race_restriction_allows(restricao, race_sources):
                return False, f"❌ Restrito a: {restricao}."

        assigned = cursor.execute(
            'SELECT extra, origem_vaga FROM player_vagas WHERE user_id = ? AND vaga_nome = ?',
            (membro.id, nome_vaga),
        ).fetchone()
        if assigned:
            assigned_extra = bool(assigned[0])
            if assigned_extra and not extra:
                if limite > 0:
                    atual = cursor.execute(
                        '''
                        SELECT COUNT(*)
                        FROM player_vagas
                        WHERE vaga_nome = ?
                          AND COALESCE(extra, 0) = 0
                        ''',
                        (nome_vaga,),
                    ).fetchone()[0]
                    if atual >= limite:
                        return False, f"❌ Vaga lotada ({atual}/{limite})."
                cursor.execute(
                    '''
                    UPDATE player_vagas
                    SET extra = 0, origem_vaga = NULL
                    WHERE user_id = ? AND vaga_nome = ?
                    ''',
                    (membro.id, nome_vaga),
                )
                conn.commit()
                return True, "✅ Convertida para vaga normal."
            return True, "✅ Já possui."

        if categoria in RACE_CATEGORIES and not extra:
            racas_antigas = cursor.execute('''
                SELECT pv.vaga_nome FROM player_vagas pv
                JOIN vagas v ON pv.vaga_nome = v.nome
                WHERE pv.user_id = ?
                  AND v.categoria IN ("Raças Normais", "Raças Especiais")
                  AND COALESCE(pv.extra, 0) = 0
            ''', (membro.id,)).fetchall()
            for (r_nome,) in racas_antigas:
                await _remove_vaga_from_member(cursor, guild, membro, r_nome, allow_initial=False)
            cursor.execute('UPDATE personagens SET raca = ? WHERE user_id = ?', (nome_vaga, membro.id))

        if limite > 0 and not extra:
            atual = cursor.execute(
                '''
                SELECT COUNT(*)
                FROM player_vagas
                WHERE vaga_nome = ?
                  AND COALESCE(extra, 0) = 0
                ''',
                (nome_vaga,),
            ).fetchone()[0]
            if atual >= limite:
                return False, f"❌ Vaga lotada ({atual}/{limite})."

        cursor.execute(
            '''
            INSERT INTO player_vagas (user_id, vaga_nome, extra, origem_vaga)
            VALUES (?, ?, ?, ?)
            ''',
            (membro.id, nome_vaga, 1 if extra else 0, origem_vaga),
        )
        _grant_vaga_points(cursor, membro.id, nome_vaga, categoria, pa_bonus, pp_bonus, pa_inicial, pp_inicial)
        
        if role_id:
            role = guild.get_role(role_id)
            if role:
                try:
                    await membro.add_roles(role)
                except discord.DiscordException:
                    logger.warning("Falha ao adicionar cargo %s ao membro %s.", role_id, membro.id)

        filhas = cursor.execute(
            'SELECT vaga_filha, extra FROM vagas_vinculo WHERE vaga_pai = ?',
            (nome_vaga,),
        ).fetchall()
        conn.commit()

    for filha, filha_extra in filhas:
        await atribuir_vaga_logica(
            guild,
            membro,
            filha,
            extra=bool(filha_extra),
            origem_vaga=nome_vaga,
        )
    return True, "✅ Sucesso"


async def remover_vaga_logica(guild, membro, nome_vaga):
    with get_connection() as conn:
        cursor = conn.cursor()
        ok, msg, removed = await _remove_vaga_from_member(cursor, guild, membro, nome_vaga, allow_initial=False)
        if ok:
            conn.commit()
        return ok, msg, removed
