import math
import sqlite3

from database import get_connection, get_pericia_bonuses, get_vagas_bonus
from utils.logic import calcular_reiatsu_efetiva, calcular_reiryoku, get_potencial_info
from utils.pericia_service import build_pericia_raca_filter, get_accessible_pericia_racas


BASE_KIDO_COST = 100
NUMBER_COST_GROWTH = 0.08
PERICIA_POWER_PER_LEVEL = 0.02
CONTROL_COST_REDUCTION_PER_LEVEL = 0.02
SHORT_CHANT_COST_MULT = 1.00
SHORT_CHANT_POWER_MULT = 1.00
FULL_CHANT_COST_MULT = 1.20
FULL_CHANT_POWER_MULT = 1.20
NO_CHANT_COST_MULT = 0.80
NO_CHANT_POWER_MULT = 0.80
NIJU_EISHO_COST_MULT = 1.20
NIJU_EISHO_POWER_MULT = 1.20

KIDO_LIMITS = {
    1: 15,
    2: 30,
    3: 50,
    4: 70,
    5: 90,
    6: 99,
}

METHODS = {
    "normal": ("normal", SHORT_CHANT_COST_MULT, SHORT_CHANT_POWER_MULT),
    "curto": ("normal", SHORT_CHANT_COST_MULT, SHORT_CHANT_POWER_MULT),
    "completo": ("encantamento", FULL_CHANT_COST_MULT, FULL_CHANT_POWER_MULT),
    "encantamento": ("encantamento", FULL_CHANT_COST_MULT, FULL_CHANT_POWER_MULT),
    "sem": ("sem encantamento", NO_CHANT_COST_MULT, NO_CHANT_POWER_MULT),
    "sem_encantamento": ("sem encantamento", NO_CHANT_COST_MULT, NO_CHANT_POWER_MULT),
    "niju": ("Nijū Eishō", NIJU_EISHO_COST_MULT, NIJU_EISHO_POWER_MULT),
    "niju_eisho": ("Nijū Eishō", NIJU_EISHO_COST_MULT, NIJU_EISHO_POWER_MULT),
}

CATEGORIES = {
    "hado": "Hadō",
    "hadō": "Hadō",
    "bakudo": "Bakudō",
    "bakudō": "Bakudō",
    "kaido": "Kaidō",
    "kaidō": "Kaidō",
    "barreira": "Barreira",
    "kido proibido": "Kidō Proibido",
    "kidō proibido": "Kidō Proibido",
}
PLAYER_KIDO_CLASSIFICATIONS = {"criado", "exclusivo", "proibido"}
KIDO_ALLOWED_RACES = ("shinigami", "vaizard", "vizard", "visored")
KAIDO_RESTORE_RULES = {
    1: (0.05, 100, 1.50),
    2: (0.05, 100, 1.50),
    3: (0.10, 300, 1.35),
    4: (0.10, 300, 1.35),
    5: (0.15, 600, 1.25),
    6: (0.15, 600, 1.25),
}


def normalize_method(value):
    if not value:
        return METHODS["normal"]
    return METHODS.get(value.lower().strip(), METHODS["normal"])


def normalize_category(value):
    return CATEGORIES.get(value.lower().strip()) if value else None


def _has_allowed_kido_race(value):
    text = (value or "").strip().casefold()
    return any(allowed in text for allowed in KIDO_ALLOWED_RACES)


def has_kido_access(user_id):
    with get_connection() as conn:
        row = conn.execute("SELECT raca FROM personagens WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return False
        racas = [row[0]]
        racas.extend(
            vaga[0]
            for vaga in conn.execute("SELECT vaga_nome FROM player_vagas WHERE user_id = ?", (user_id,)).fetchall()
            if vaga and vaga[0]
        )
    return any(_has_allowed_kido_race(raca) for raca in racas)


def has_shinigami_character(user_id):
    return has_kido_access(user_id)


def normalize_classification(value):
    normalized = (value or "").lower().strip()
    if normalized in ("oficial", "oficiais"):
        return "oficial"
    if normalized in ("criado", "criados", "player", "jogador", "comum", "comuns", "common"):
        return "criado"
    if normalized in ("proibido", "proibidos", "forbidden"):
        return "proibido"
    if normalized in ("exclusivo", "exclusivos", "exclusive"):
        return "exclusivo"
    return None


def parse_percent(value):
    try:
        text = str(value).strip().replace("%", "").replace(",", ".")
        number = float(text)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number / 100 if number > 1 else number


def create_kido_tecnica(nome, categoria, numero, classificacao, criador_id=None, descricao="", dano_bonus=None):
    nome = nome.strip()
    descricao = descricao.strip()
    category_label = normalize_category(categoria)
    class_label = normalize_classification(classificacao)
    if not nome:
        return False, "Nome do Kido nao pode ficar vazio.", None
    if not category_label:
        return False, "Categoria invalida. Use hado, bakudo ou kaido.", None
    if not class_label:
        return False, "Classificacao invalida. Use oficial, criado, exclusivo ou proibido.", None
    if numero < 1 or numero > 99:
        return False, "O numero do Kido deve ficar entre 1 e 99.", None
    if class_label == "criado" and not criador_id:
        return False, "Kido criado precisa de um criador.", None
    if class_label in PLAYER_KIDO_CLASSIFICATIONS and criador_id and not has_shinigami_character(criador_id):
        return False, "Apenas personagens Shinigami ou Vaizard podem criar Kido.", None
    parsed_bonus = None if dano_bonus in (None, "") else parse_percent(dano_bonus)
    if dano_bonus not in (None, "") and parsed_bonus is None:
        return False, "Bonus de potencia invalido. Use porcentagem, exemplo: 50.", None
    if parsed_bonus is not None and parsed_bonus > 3:
        return False, "Bonus de potencia alto demais. Use ate 300%.", None

    with get_connection() as conn:
        duplicate = conn.execute(
            """
            SELECT id
            FROM kido_tecnicas
            WHERE LOWER(nome) = LOWER(?)
              AND categoria = ?
              AND numero = ?
              AND classificacao = ?
              AND COALESCE(criador_id, 0) = COALESCE(?, 0)
            """,
            (nome, category_label, numero, class_label, criador_id),
        ).fetchone()
        if duplicate:
            return False, f"Kido ja cadastrado com ID {duplicate[0]}.", duplicate[0]

        cursor = conn.execute(
            """
            INSERT INTO kido_tecnicas (nome, categoria, numero, classificacao, criador_id, descricao, dano_bonus)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (nome, category_label, numero, class_label, criador_id, descricao, parsed_bonus),
        )
        conn.commit()
        tecnica_id = cursor.lastrowid

    return True, "Kido registrado.", tecnica_id


def list_kido_tecnicas(classificacao, user_id=None, include_private=False):
    class_label = normalize_classification(classificacao)
    if not class_label:
        return []

    query = """
        SELECT MIN(id) AS id, nome, categoria, numero, classificacao, criador_id, descricao, dano_bonus
        FROM kido_tecnicas
        WHERE classificacao = ?
    """
    params = [class_label]
    if class_label in PLAYER_KIDO_CLASSIFICATIONS and not include_private:
        query += " AND criador_id = ?"
        params.append(user_id)
    query += """
        GROUP BY LOWER(nome), categoria, numero, classificacao, COALESCE(criador_id, 0)
        ORDER BY categoria COLLATE NOCASE, numero, nome COLLATE NOCASE
    """

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_kido_tecnica(tecnica_id, user_id=None):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, nome, categoria, numero, classificacao, criador_id, descricao, dano_bonus
            FROM kido_tecnicas
            WHERE id = ?
            """,
            (tecnica_id,),
        ).fetchone()
    if not row:
        return None
    tecnica = dict(row)
    if user_id is None:
        return tecnica
    if not has_shinigami_character(user_id):
        return None
    if tecnica["classificacao"] == "oficial":
        return tecnica
    if tecnica["classificacao"] in PLAYER_KIDO_CLASSIFICATIONS and tecnica["criador_id"] == user_id:
        return tecnica
    return None


def grant_kido_tecnica(user_id, tecnica_id):
    if not has_shinigami_character(user_id):
        return False, "Apenas personagens Shinigami ou Vaizard podem receber Kido exclusivo ou proibido.", None

    source = get_kido_tecnica(tecnica_id)
    if not source:
        return False, "Kido nao encontrado.", None
    if source["classificacao"] not in ("exclusivo", "proibido"):
        return False, "Use este comando apenas para Kidō exclusivos ou proibidos.", None
    if source.get("criador_id") == user_id:
        return True, "Este jogador ja possui esse Kido.", source["id"]

    with get_connection() as conn:
        duplicate = conn.execute(
            """
            SELECT id
            FROM kido_tecnicas
            WHERE LOWER(nome) = LOWER(?)
              AND categoria = ?
              AND numero = ?
              AND classificacao = ?
              AND criador_id = ?
            """,
            (source["nome"], source["categoria"], source["numero"], source["classificacao"], user_id),
        ).fetchone()
        if duplicate:
            return True, "Este jogador ja possui esse Kido.", duplicate[0]

        cursor = conn.execute(
            """
            INSERT INTO kido_tecnicas (nome, categoria, numero, classificacao, criador_id, descricao, dano_bonus)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source["nome"],
                source["categoria"],
                source["numero"],
                source["classificacao"],
                user_id,
                source.get("descricao") or "",
                source.get("dano_bonus"),
            ),
        )
        conn.commit()
        granted_id = cursor.lastrowid

    return True, "Kido atribuido.", granted_id


def get_kido_tier(user_id):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        racas = get_accessible_pericia_racas(user_id, conn)
        raca_filter, raca_params = build_pericia_raca_filter("pb.raca", racas)
        row = conn.execute(
            f"""
            SELECT COALESCE(pp.nivel, 1) AS nivel
            FROM pericias_base pb
            LEFT JOIN player_pericias pp ON pb.id = pp.pericia_id AND pp.user_id = ?
            WHERE LOWER(REPLACE(pb.nome, 'ō', 'o')) = 'kido'
              AND {raca_filter}
            ORDER BY COALESCE(pp.nivel, 1) DESC
            LIMIT 1
            """,
            (user_id, *raca_params),
        ).fetchone()
    return row["nivel"] if row else 1


def get_max_reiryoku(user_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT forca, velocidade, resistencia FROM personagens WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None

    vagas = get_vagas_bonus(user_id)
    pericias = get_pericia_bonuses(user_id)
    total = calcular_reiryoku(
        row[0] + vagas["forca"]["fixo"],
        row[1] + vagas["velocidade"]["fixo"],
        row[2] + vagas["resistencia"]["fixo"],
    )
    return int(total * (1.0 + pericias.get("reiryoku", 0.0)))


def get_reiatsu_value(user_id):
    state = ensure_kido_state(user_id)
    if not state:
        return None

    vagas = get_vagas_bonus(user_id)
    pericias = get_pericia_bonuses(user_id)
    mult_potencial, _, _ = get_potencial_info(user_id)
    multiplicador = (1.0 + vagas["forca"]["mult"] + pericias.get("forca", 0.0) + pericias.get("reiatsu", 0.0)) * mult_potencial
    return calcular_reiatsu_efetiva(state["reiryoku_atual"], state["reiryoku_max"], multiplicador)


def ensure_kido_state(user_id):
    max_reiryoku = get_max_reiryoku(user_id)
    if max_reiryoku is None:
        return None

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        state = conn.execute("SELECT * FROM kido_estado WHERE user_id = ?", (user_id,)).fetchone()
        if not state:
            conn.execute(
                "INSERT INTO kido_estado (user_id, reiryoku_atual) VALUES (?, ?)",
                (user_id, max_reiryoku),
            )
            conn.commit()
            state = conn.execute("SELECT * FROM kido_estado WHERE user_id = ?", (user_id,)).fetchone()
        elif state["reiryoku_atual"] is None or state["reiryoku_atual"] > max_reiryoku:
            conn.execute(
                "UPDATE kido_estado SET reiryoku_atual = ? WHERE user_id = ?",
                (max_reiryoku, user_id),
            )
            conn.commit()
            state = conn.execute("SELECT * FROM kido_estado WHERE user_id = ?", (user_id,)).fetchone()

    return dict(state) | {"reiryoku_max": max_reiryoku}


def calculate_kido(user_id, numero, metodo="normal"):
    tier = get_kido_tier(user_id)
    method_label, cost_mult, power_mult = normalize_method(metodo)
    base_cost = BASE_KIDO_COST * ((1 + NUMBER_COST_GROWTH) ** max(0, numero - 1))
    control_reduction = max(0.0, 1.0 - (CONTROL_COST_REDUCTION_PER_LEVEL * (tier - 1)))
    cost = max(1, math.ceil(base_cost * cost_mult * control_reduction))
    pericia_bonus = PERICIA_POWER_PER_LEVEL * (tier - 1)
    cooldown = max(1, math.ceil(numero / 20))
    return {
        "tier": tier,
        "max_number": KIDO_LIMITS.get(tier, 15),
        "method": method_label,
        "cost": cost,
        "pericia_bonus": pericia_bonus,
        "power_multiplier": power_mult,
        "cooldown": cooldown,
    }


def get_last_kido_power(user_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT poder
            FROM kido_usos
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def list_known_kido_tecnicas(user_id, classificacao):
    class_label = normalize_classification(classificacao)
    if not class_label or not has_shinigami_character(user_id):
        return []

    if class_label == "oficial":
        max_number = calculate_kido(user_id, 1)["max_number"]
        return [
            tecnica
            for tecnica in list_kido_tecnicas("oficial", include_private=True)
            if tecnica["numero"] <= max_number
        ]

    if class_label in PLAYER_KIDO_CLASSIFICATIONS:
        return list_kido_tecnicas(class_label, user_id, include_private=False)

    return []


def _build_kido_result(user_id, category_label, numero, metodo="normal", tecnica=None):
    data = calculate_kido(user_id, numero, metodo)
    reiatsu = get_reiatsu_value(user_id)
    if reiatsu is None:
        return False, "Personagem nao encontrado.", None

    technique_bonus = float((tecnica or {}).get("dano_bonus") or 0.0)
    total_bonus = technique_bonus + data["pericia_bonus"]
    damage = int(reiatsu * (1.0 + total_bonus) * data["power_multiplier"])
    data.update(
        {
            "category": category_label,
            "number": numero,
            "reiatsu": reiatsu,
            "technique_bonus": technique_bonus,
            "total_bonus": total_bonus,
            "damage": damage,
        }
    )
    if tecnica:
        data["tecnica"] = tecnica
    return True, "", data


def use_kido(user_id, categoria, numero, metodo="normal", tecnica=None):
    if not has_shinigami_character(user_id):
        return False, "Apenas personagens Shinigami ou Vaizard podem usar Kido.", None

    category_label = normalize_category(categoria)
    if not category_label:
        return False, "Categoria invalida. Use hado, bakudo ou kaido.", None
    if numero < 1 or numero > 99:
        return False, "O numero do Kido deve ficar entre 1 e 99.", None

    state = ensure_kido_state(user_id)
    if not state:
        return False, "Personagem nao encontrado.", None

    ok, msg, data = _build_kido_result(user_id, category_label, numero, metodo, tecnica)
    if not ok:
        return False, msg, data
    if numero > data["max_number"]:
        return False, f"Seu Tier {data['tier']} de Kido permite usar ate o #{data['max_number']}.", data
    if state["cooldown"] > 0:
        return False, f"Seu Kido esta em cooldown por mais {state['cooldown']} turno(s).", data
    if state["reiryoku_atual"] < data["cost"]:
        return False, f"Reiryoku insuficiente: {state['reiryoku_atual']}/{data['cost']}.", data

    ultimo_kido = f"{category_label} #{numero}"
    tecnica_id = None
    if tecnica:
        ultimo_kido = f"{tecnica['nome']} ({category_label} #{numero})"
        tecnica_id = tecnica["id"]

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE kido_estado
            SET reiryoku_atual = reiryoku_atual - ?, cooldown = ?, usos_total = usos_total + 1,
                gasto_total = gasto_total + ?, poder_total = poder_total + ?, ultimo_kido = ?, ultimo_poder = ?
            WHERE user_id = ?
            """,
            (data["cost"], data["cooldown"], data["cost"], data["damage"], ultimo_kido, data["damage"], user_id),
        )
        conn.execute(
            """
            INSERT INTO kido_usos (user_id, categoria, numero, metodo, custo, poder, cooldown, tecnica_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, category_label, numero, data["method"], data["cost"], data["damage"], data["cooldown"], tecnica_id),
        )
        conn.commit()

    new_state = ensure_kido_state(user_id)
    data.update({"state": new_state})
    return True, "Kido conjurado.", data


def use_kido_tecnica(user_id, tecnica_id, metodo="normal"):
    tecnica = get_kido_tecnica(tecnica_id, user_id)
    if not tecnica:
        return False, "Kido indisponivel para este usuario.", None
    return use_kido(user_id, tecnica["categoria"], tecnica["numero"], metodo, tecnica)


def get_kaido_rule(tier):
    return KAIDO_RESTORE_RULES.get(max(1, min(6, int(tier or 1))), KAIDO_RESTORE_RULES[1])


def calculate_kaido_heal(tier, target_reiryoku_max):
    percent, minimum, cost_multiplier = get_kaido_rule(tier)
    restore = max(minimum, math.ceil(max(0, int(target_reiryoku_max or 0)) * percent))
    cost = max(1, math.ceil(restore * cost_multiplier))
    return restore, cost, percent, cost_multiplier


def use_kaido_heal(user_id, target_id=None):
    if not has_shinigami_character(user_id):
        return False, "Apenas personagens Shinigami ou Vaizard podem usar Kido.", None

    target_id = target_id or user_id
    state = ensure_kido_state(user_id)
    if not state:
        return False, "Personagem nao encontrado.", None
    if state["cooldown"] > 0:
        return False, f"Seu Kido esta em cooldown por mais {state['cooldown']} turno(s).", None

    target_state = ensure_kido_state(target_id)
    if not target_state:
        return False, "Alvo nao encontrado.", None

    tier = get_kido_tier(user_id)
    reiatsu = get_reiatsu_value(user_id)
    if reiatsu is None:
        return False, "Personagem nao encontrado.", None

    restore_amount, cost, restore_percent, cost_multiplier = calculate_kaido_heal(tier, target_state["reiryoku_max"])
    missing_before = max(0, target_state["reiryoku_max"] - target_state["reiryoku_atual"])
    if missing_before <= 0:
        return False, "O alvo ja esta com Reiryoku cheio.", None
    if state["reiryoku_atual"] < cost:
        return False, f"Reiryoku insuficiente para canalizar Kaido: {state['reiryoku_atual']}/{cost}.", None

    if target_id == user_id:
        reiryoku_after_cost = max(0, state["reiryoku_atual"] - cost)
        restored = min(restore_amount, max(0, state["reiryoku_max"] - reiryoku_after_cost))
        target_reiryoku = min(state["reiryoku_max"], reiryoku_after_cost + restored)
    else:
        restored = min(restore_amount, missing_before)
        target_reiryoku = target_state["reiryoku_atual"] + restored
    cooldown = 1
    ultimo_kido = f"Kaidō: Curar (+{restored}/{restore_amount} Reiryoku)"

    with get_connection() as conn:
        if target_id == user_id:
            conn.execute(
                """
                UPDATE kido_estado
                SET reiryoku_atual = ?, cooldown = ?, usos_total = usos_total + 1,
                    gasto_total = gasto_total + ?, poder_total = poder_total + ?, ultimo_kido = ?, ultimo_poder = ?
                WHERE user_id = ?
                """,
                (target_reiryoku, cooldown, cost, restored, ultimo_kido, restored, user_id),
            )
        else:
            conn.execute(
                """
                UPDATE kido_estado
                SET reiryoku_atual = reiryoku_atual - ?, cooldown = ?, usos_total = usos_total + 1,
                    gasto_total = gasto_total + ?, poder_total = poder_total + ?, ultimo_kido = ?, ultimo_poder = ?
                WHERE user_id = ?
            """,
                (cost, cooldown, cost, restored, ultimo_kido, restored, user_id),
            )
            conn.execute(
                "UPDATE kido_estado SET reiryoku_atual = ? WHERE user_id = ?",
                (target_reiryoku, target_id),
            )
        conn.execute(
            """
            INSERT INTO kido_usos (user_id, categoria, numero, metodo, custo, poder, cooldown, tecnica_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, "Kaidō", 0, "curar", cost, restored, cooldown, None),
        )
        conn.commit()

    data = {
        "action": "heal",
        "method": "curar",
        "category": "Kaidō",
        "tier": tier,
        "cost": cost,
        "heal": restore_amount,
        "restored": restored,
        "restore_percent": restore_percent,
        "cost_multiplier": cost_multiplier,
        "reiatsu": reiatsu,
        "cooldown": cooldown,
        "state": ensure_kido_state(user_id),
        "target_state": ensure_kido_state(target_id),
        "target_id": target_id,
    }
    return True, "Cura de Kaido realizada.", data


def use_niju_eisho(user_id, tecnica_ids):
    if not has_shinigami_character(user_id):
        return False, "Apenas personagens Shinigami ou Vaizard podem usar Kido.", None

    unique_ids = []
    for tecnica_id in tecnica_ids:
        try:
            parsed = int(tecnica_id)
        except (TypeError, ValueError):
            return False, "Selecao de Kido invalida.", None
        if parsed not in unique_ids:
            unique_ids.append(parsed)

    if len(unique_ids) != 2:
        return False, "Nijū Eishō precisa de exatamente dois Kidō diferentes.", None

    tier = get_kido_tier(user_id)
    if tier < 3:
        return False, "Nijū Eishō exige Tier III em Kido.", None

    state = ensure_kido_state(user_id)
    if not state:
        return False, "Personagem nao encontrado.", None
    if state["cooldown"] > 0:
        return False, f"Seu Kido esta em cooldown por mais {state['cooldown']} turno(s).", None

    results = []
    for tecnica_id in unique_ids:
        tecnica = get_kido_tecnica(tecnica_id, user_id)
        if not tecnica:
            return False, "Um dos Kidō selecionados esta indisponivel para este usuario.", None

        category_label = normalize_category(tecnica["categoria"])
        if not category_label:
            return False, "Categoria invalida em um dos Kidō selecionados.", None

        ok, msg, data = _build_kido_result(
            user_id,
            category_label,
            tecnica["numero"],
            "niju_eisho",
            tecnica,
        )
        if not ok:
            return False, msg, data
        if tecnica["numero"] > data["max_number"]:
            return False, f"Seu Tier {data['tier']} de Kido permite usar ate o #{data['max_number']}.", data
        results.append(data)

    total_cost = sum(item["cost"] for item in results)
    total_damage = sum(item["damage"] for item in results)
    cooldown = max(item["cooldown"] for item in results)
    if state["reiryoku_atual"] < total_cost:
        return False, f"Reiryoku insuficiente: {state['reiryoku_atual']}/{total_cost}.", {
            "method": "Nijū Eishō",
            "cost": total_cost,
            "damage": total_damage,
            "cooldown": cooldown,
            "techniques": results,
        }

    names = [f"{item['tecnica']['nome']} ({item['category']} #{item['number']})" for item in results]
    ultimo_kido = "Nijū Eishō: " + " + ".join(names)

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE kido_estado
            SET reiryoku_atual = reiryoku_atual - ?, cooldown = ?, usos_total = usos_total + 2,
                gasto_total = gasto_total + ?, poder_total = poder_total + ?, ultimo_kido = ?, ultimo_poder = ?
            WHERE user_id = ?
            """,
            (total_cost, cooldown, total_cost, total_damage, ultimo_kido, total_damage, user_id),
        )
        for item in results:
            conn.execute(
                """
                INSERT INTO kido_usos (user_id, categoria, numero, metodo, custo, poder, cooldown, tecnica_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    item["category"],
                    item["number"],
                    item["method"],
                    item["cost"],
                    item["damage"],
                    item["cooldown"],
                    item["tecnica"]["id"],
                ),
            )
        conn.commit()

    return True, "Nijū Eishō conjurado.", {
        "method": "Nijū Eishō",
        "cost": total_cost,
        "damage": total_damage,
        "cooldown": cooldown,
        "techniques": results,
        "state": ensure_kido_state(user_id),
    }


def pass_kido_turn(user_id, recover=0):
    state = ensure_kido_state(user_id)
    if not state:
        return None
    max_reiryoku = state["reiryoku_max"]
    new_cd = max(0, state["cooldown"] - 1)
    new_reiryoku = min(max_reiryoku, state["reiryoku_atual"] + max(0, recover))
    with get_connection() as conn:
        conn.execute(
            "UPDATE kido_estado SET cooldown = ?, reiryoku_atual = ? WHERE user_id = ?",
            (new_cd, new_reiryoku, user_id),
        )
        conn.commit()
    return ensure_kido_state(user_id)


def rest_kido(user_id):
    state = ensure_kido_state(user_id)
    if not state:
        return None
    with get_connection() as conn:
        conn.execute(
            "UPDATE kido_estado SET reiryoku_atual = ?, cooldown = 0 WHERE user_id = ?",
            (state["reiryoku_max"], user_id),
        )
        conn.commit()
    return ensure_kido_state(user_id)
