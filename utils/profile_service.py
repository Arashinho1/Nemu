import math

from database import PASSIVE_RACE_CATEGORIES, get_connection, get_vagas_bonus, get_pericia_bonuses
from utils.attribute_math import (
    non_passive_multiplier,
    passive_attribute_value,
    passive_attributes,
    reiatsu_multiplier as build_reiatsu_multiplier,
)
from utils.logic import (
    calcular_reiatsu,
    calcular_reiatsu_efetiva,
    calcular_reiatsu_maxima,
    calcular_reiryoku,
    format_reiatsu_limit,
    get_potencial_effects,
    nivel_reiatsu,
    reiatsu_cap_for_limit_index,
)


ATTRIBUTES = {
    "forca": "Forca",
    "velocidade": "Velocidade",
    "resistencia": "Resistencia",
}
SPECIAL_BONUS_LABELS = {
    "reiryoku": "Reiryoku",
    "reiatsu": "Reiatsu",
}

def _attribute_targets(attr_text):
    targets = []
    aliases = {
        "força": "forca",
        "resistência": "resistencia",
        "todos": "todos",
        "todas": "todos",
        "fisicos": "todos",
        "físicos": "todos",
    }
    for item in (attr_text or "").replace("+", ",").split(","):
        target = item.strip().lower()
        if not target or target.startswith(("tecnica:", "turnos:")):
            continue
        target = aliases.get(target, target)
        if target == "todos":
            for physical in ATTRIBUTES:
                if physical not in targets:
                    targets.append(physical)
            continue
        if target not in targets:
            targets.append(target)
    return targets


def _format_percent(value):
    percent = value * 100
    return f"{percent:.0f}%" if percent.is_integer() else f"{percent:.1f}%"


def _modifier_label(modifier):
    value = modifier["value"]
    suffix = " passivo" if modifier.get("source") == "raca_passiva" else ""
    if modifier["type"] == "percent":
        return f"{modifier['name']} +{_format_percent(value / 100)}{suffix}"
    if modifier["type"] == "multiplier":
        return f"{modifier['name']} x{value:.2f}{suffix}"
    return f"{modifier['name']} +{int(value)}{suffix}"


def _modifier_total_text(modifiers):
    if not modifiers:
        return "Sem modificadores"
    passive = sum(1 for modifier in modifiers if modifier.get("source") == "raca_passiva")
    active = len(modifiers) - passive
    if passive and not active:
        return f"{passive} bonus racial passivo" + ("" if passive == 1 else "s")
    if passive and active:
        passive_text = f"{passive} passivo" + ("" if passive == 1 else "s")
        active_text = f"{active} ativo" + ("" if active == 1 else "s")
        return f"{passive_text}, {active_text}"
    return f"{len(modifiers)} modificador" + ("" if len(modifiers) == 1 else "es") + " ativo" + ("" if len(modifiers) == 1 else "s")


def _get_manual_modifiers(conn, user_id, attr_key):
    try:
        rows = conn.execute(
            """
            SELECT nome, tipo, valor, origem
            FROM attribute_modifiers
            WHERE user_id = ? AND atributo = ? AND ativo = 1
            ORDER BY id
            """,
            (user_id, attr_key),
        ).fetchall()
    except Exception:
        return []
    return [
        {
            "name": nome,
            "type": tipo,
            "value": float(valor),
            "source": origem or "manual",
        }
        for nome, tipo, valor, origem in rows
    ]


def _get_structured_modifiers(conn, user_id, attr_key, mult_potencial, potencial_nome, potencial_ativo):
    modifiers = []

    vagas = conn.execute(
        """
        SELECT v.nome, v.multiplicador, v.bonus_fixo, v.atributo, v.categoria
        FROM player_vagas pv
        JOIN vagas v ON pv.vaga_nome = v.nome
        WHERE pv.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    for nome, mult, fixo, targets, categoria in vagas:
        target_list = _attribute_targets(targets)
        if attr_key not in target_list:
            continue
        source = "raca_passiva" if categoria in PASSIVE_RACE_CATEGORIES else "vaga"
        if fixo:
            modifiers.append({"name": nome, "type": "flat", "value": int(fixo), "source": source})
        if mult:
            modifiers.append({"name": nome, "type": "percent", "value": round(float(mult) * 100, 2), "source": source})

    pericias = conn.execute(
        """
        SELECT pb.nome, pb.bonus_valor, pp.nivel, pb.atributo_afetado
        FROM player_pericias pp
        JOIN pericias_base pb ON pp.pericia_id = pb.id
        WHERE pp.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    for nome, bonus_valor, nivel, atributo_afetado in pericias:
        if attr_key not in _attribute_targets(atributo_afetado) or bonus_valor is None:
            continue
        total = bonus_valor * (nivel - 1)
        if total > 0:
            modifiers.append({"name": nome, "type": "percent", "value": round(float(total) * 100, 2), "source": "pericia"})

    if potencial_ativo and mult_potencial > 1.0:
        modifiers.append({"name": potencial_nome, "type": "multiplier", "value": float(mult_potencial), "source": "potencial"})

    modifiers.extend(_get_manual_modifiers(conn, user_id, attr_key))
    return modifiers


def _get_bonus_sources(conn, user_id, attr_key, mult_potencial, potencial_nome, potencial_ativo):
    modifiers = _get_structured_modifiers(conn, user_id, attr_key, mult_potencial, potencial_nome, potencial_ativo)
    return [_modifier_label(modifier) for modifier in modifiers]


def _get_special_bonus_sources(conn, user_id, attr_key):
    sources = []
    pericias = conn.execute(
        """
        SELECT pb.nome, pb.bonus_valor, pp.nivel, pb.atributo_afetado
        FROM player_pericias pp
        JOIN pericias_base pb ON pp.pericia_id = pb.id
        WHERE pp.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    for nome, bonus_valor, nivel, atributo_afetado in pericias:
        if attr_key not in _attribute_targets(atributo_afetado) or bonus_valor is None:
            continue
        total = bonus_valor * (nivel - 1)
        if total > 0:
            sources.append(f"{nome} +{_format_percent(total)}")
    return sources


def _sync_reiryoku_state(user_id, max_reiryoku):
    with get_connection() as conn:
        state = conn.execute("SELECT reiryoku_atual FROM kido_estado WHERE user_id = ?", (user_id,)).fetchone()
        if not state:
            conn.execute(
                "INSERT INTO kido_estado (user_id, reiryoku_atual) VALUES (?, ?)",
                (user_id, max_reiryoku),
            )
            conn.commit()
            return max_reiryoku

        current = state[0]
        if current is None or current > max_reiryoku:
            conn.execute(
                "UPDATE kido_estado SET reiryoku_atual = ? WHERE user_id = ?",
                (max_reiryoku, user_id),
            )
            conn.commit()
            return max_reiryoku
        return current


def get_profile_data(user_id):
    user_id = int(user_id)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT nome, raca, forca, velocidade, resistencia, pontos_livres,
                   limite_nivel, pontos_pericia
            FROM personagens
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

    if not row:
        return None

    nome, raca, forca, velocidade, resistencia, pontos_livres, limite_idx, pontos_pericia = row
    with get_connection() as conn:
        vagas_bonus = get_vagas_bonus(user_id)
        pericia_bonus = get_pericia_bonuses(user_id)
        potencial_effects = get_potencial_effects(user_id)
        potencial_nome = potencial_effects["names"]
        potencial_ativo = potencial_effects["active"]

        def attr_payload(key, base):
            bonus = vagas_bonus[key]
            mult_potencial = potencial_effects["multipliers"].get(key, 1.0)
            potencial_attr_nome = potencial_effects["source_names"].get(key) or potencial_nome
            manual_mods = _get_manual_modifiers(conn, user_id, key)
            manual_flat = sum(mod["value"] for mod in manual_mods if mod["type"] == "flat")
            manual_percent = sum(mod["value"] / 100 for mod in manual_mods if mod["type"] == "percent")
            manual_multiplier = 1.0
            for mod in manual_mods:
                if mod["type"] == "multiplier":
                    manual_multiplier *= mod["value"]
            passive_value = passive_attribute_value(base, bonus)
            mult = (
                1.0
                + non_passive_multiplier(bonus)
                + pericia_bonus.get(key, 0.0)
                + manual_percent
            ) * mult_potencial * manual_multiplier
            final = int((passive_value + manual_flat) * mult)
            modifiers = _get_structured_modifiers(conn, user_id, key, mult_potencial, potencial_attr_nome, potencial_ativo)
            return {
                "key": key,
                "label": ATTRIBUTES[key],
                "base": base,
                "passive": passive_value,
                "final": final,
                "bonus": final - base,
                "fixed_bonus": bonus["fixo"],
                "multiplier": mult,
                "modifiers": modifiers,
                "modifier_summary": _modifier_total_text(modifiers),
                "bonus_sources": [_modifier_label(modifier) for modifier in modifiers],
            }

        attributes = {
            "forca": attr_payload("forca", forca),
            "velocidade": attr_payload("velocidade", velocidade),
            "resistencia": attr_payload("resistencia", resistencia),
        }

    permanent_attrs = passive_attributes(
        {"forca": forca, "velocidade": velocidade, "resistencia": resistencia},
        vagas_bonus,
    )
    reiryoku_base = calcular_reiryoku(
        permanent_attrs["forca"],
        permanent_attrs["velocidade"],
        permanent_attrs["resistencia"],
    )
    reiryoku_mult = 1.0 + pericia_bonus.get("reiryoku", 0.0)
    reiryoku_max = int(reiryoku_base * reiryoku_mult)
    reiryoku = _sync_reiryoku_state(user_id, reiryoku_max)
    reiatsu_mult = build_reiatsu_multiplier(
        vagas_bonus["forca"],
        pericia_bonus,
        potencial_effects["multipliers"].get("forca", 1.0),
    )
    reiatsu_max = calcular_reiatsu_maxima(reiryoku_max, reiatsu_mult)
    reiatsu = calcular_reiatsu_efetiva(reiryoku, reiryoku_max, reiatsu_mult)
    cap = reiatsu_cap_for_limit_index(limite_idx)
    cap_payload = None if math.isinf(float(cap)) else cap

    return {
        "user_id": user_id,
        "nome": nome,
        "raca": raca,
        "attributes": attributes,
        "pontos_livres": pontos_livres,
        "pontos_pericia": pontos_pericia,
        "reiryoku": reiryoku,
        "reiryoku_max": reiryoku_max,
        "reiatsu": reiatsu,
        "reiatsu_max": reiatsu_max,
        "reiatsu_cap": cap_payload,
        "reiatsu_cap_label": format_reiatsu_limit(cap),
        "reiatsu_percent": min(100, int((reiatsu / reiatsu_max) * 100)) if reiatsu_max else 0,
        "nivel": nivel_reiatsu(reiatsu_max, limite_idx),
        "potencial_nome": potencial_nome or "Nenhum",
        "potencial_ativo": potencial_ativo,
        "special_bonuses": {
            "reiryoku": {
                "label": SPECIAL_BONUS_LABELS["reiryoku"],
                "base": reiryoku_base,
                "final": reiryoku_max,
                "bonus": reiryoku_max - reiryoku_base,
                "bonus_sources": _get_special_bonus_sources(conn, user_id, "reiryoku"),
            },
            "reiatsu": {
                "label": SPECIAL_BONUS_LABELS["reiatsu"],
                "bonus_sources": _get_special_bonus_sources(conn, user_id, "reiatsu"),
            },
        },
    }


def distribute_attribute(user_id, attribute, amount, return_details=False):
    user_id = int(user_id)
    attribute = attribute.lower()
    if attribute not in ATTRIBUTES:
        result = (False, "Atributo invalido.")
        return (*result, None) if return_details else result

    try:
        amount = int(amount)
    except (TypeError, ValueError):
        result = (False, "Quantidade invalida.")
        return (*result, None) if return_details else result

    if amount <= 0:
        result = (False, "A quantidade deve ser maior que zero.")
        return (*result, None) if return_details else result

    with get_connection() as conn:
        row = conn.execute(
            "SELECT pontos_livres, forca, velocidade, resistencia, limite_nivel FROM personagens WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            result = (False, "Personagem nao encontrado.")
            return (*result, None) if return_details else result

        pontos_livres, forca, velocidade, resistencia, limite_idx = row
        if amount > pontos_livres:
            result = (False, "Pontos insuficientes.")
            return (*result, None) if return_details else result

        vagas_bonus = get_vagas_bonus(user_id)
        pericia_bonus = get_pericia_bonuses(user_id)

        new_forca = forca + (amount if attribute == "forca" else 0)
        new_velocidade = velocidade + (amount if attribute == "velocidade" else 0)
        new_resistencia = resistencia + (amount if attribute == "resistencia" else 0)

        permanent_attrs = passive_attributes(
            {"forca": new_forca, "velocidade": new_velocidade, "resistencia": new_resistencia},
            vagas_bonus,
        )
        reiryoku = calcular_reiryoku(
            permanent_attrs["forca"],
            permanent_attrs["velocidade"],
            permanent_attrs["resistencia"],
        )
        reiryoku = int(reiryoku * (1.0 + pericia_bonus.get("reiryoku", 0.0)))
        reiatsu = calcular_reiatsu(
            reiryoku,
            build_reiatsu_multiplier(vagas_bonus["forca"], pericia_bonus),
        )
        cap = reiatsu_cap_for_limit_index(limite_idx)
        if reiatsu > cap:
            result = (False, f"Limite de alma alcancado. Reiatsu ficaria {reiatsu}, acima do teto {cap}.")
            return (*result, None) if return_details else result

        conn.execute(
            f"UPDATE personagens SET pontos_livres = pontos_livres - ?, {attribute} = {attribute} + ? WHERE user_id = ?",
            (amount, amount, user_id),
        )
        conn.commit()

    details = {
        "pool_label": "PA disponíveis",
        "pool_before": pontos_livres,
        "pool_after": pontos_livres - amount,
        "target_label": ATTRIBUTES[attribute],
        "target_before": {"forca": forca, "velocidade": velocidade, "resistencia": resistencia}[attribute],
        "target_after": {"forca": new_forca, "velocidade": new_velocidade, "resistencia": new_resistencia}[attribute],
    }
    result = (True, f"+{amount} em {ATTRIBUTES[attribute]} aplicado.")
    return (*result, details) if return_details else result
