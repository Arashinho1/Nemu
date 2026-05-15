import sqlite3
import unicodedata

from database import get_connection


MAX_PERICIA_LEVEL = 6
PHYSICAL_TARGETS = ("forca", "velocidade", "resistencia")
SPECIAL_TARGETS = ("reiryoku", "reiatsu", "kido")
VALID_TARGETS = set(PHYSICAL_TARGETS + SPECIAL_TARGETS)
TARGET_ALIASES = {
    "forca": "forca",
    "força": "forca",
    "velocidade": "velocidade",
    "resistencia": "resistencia",
    "resistência": "resistencia",
    "reiryoku": "reiryoku",
    "reiatsu": "reiatsu",
    "kido": "kido",
    "kidō": "kido",
}
TARGET_LABELS = {
    "forca": "Forca",
    "velocidade": "Velocidade",
    "resistencia": "Resistencia",
    "reiryoku": "Reiryoku",
    "reiatsu": "Reiatsu",
    "kido": "Kido",
}


def _value(row, key, index=0):
    if isinstance(row, sqlite3.Row):
        return row[key]
    return row[index]


def _raca_key(value):
    return (value or "").strip().casefold()


def _target_key(value):
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.strip().casefold()


def _normalize_plain_target(value):
    text = (value or "").strip()
    alias = TARGET_ALIASES.get(text.lower())
    if alias:
        return alias
    key = _target_key(text)
    if key in ("todos", "todas", "fisicos", "fisicas"):
        return "todos"
    return TARGET_ALIASES.get(key)


def normalize_pericia_target(value):
    text = (value or "").strip()
    if not text:
        return None

    if ":" in text:
        prefix, name = text.split(":", 1)
        prefix_key = _target_key(prefix)
        name = name.strip()
        if not name:
            return None
        if prefix_key in ("tecnica", "tecnicas"):
            return f"tecnica:{name}"
        if prefix_key in ("turno", "turnos"):
            return f"turnos:{name}"
        return None

    normalized_targets = []
    for raw in text.replace("+", ",").split(","):
        target = _normalize_plain_target(raw)
        if not target:
            return None
        if target == "todos":
            for physical in PHYSICAL_TARGETS:
                if physical not in normalized_targets:
                    normalized_targets.append(physical)
            continue
        if target not in normalized_targets:
            normalized_targets.append(target)

    return ",".join(normalized_targets) if normalized_targets else None


def split_pericia_targets(value):
    target = normalize_pericia_target(value)
    if not target:
        return []
    if target.startswith(("tecnica:", "turnos:")):
        return [target]
    return [item for item in target.split(",") if item]


def format_pericia_target(value):
    targets = split_pericia_targets(value)
    if not targets:
        return "atributo"
    target = targets[0]
    if target.startswith("tecnica:"):
        return "técnicas " + target.split(":", 1)[1]
    if target.startswith("turnos:"):
        return "turnos de " + target.split(":", 1)[1]
    return ", ".join(TARGET_LABELS.get(item, item.capitalize()) for item in targets)


def split_raca_list(value):
    if isinstance(value, str):
        raw_values = value.replace("+", ",").split(",")
    else:
        raw_values = value or []
    return [str(item).strip() for item in raw_values if str(item).strip()]


def _raca_sql_key(value):
    return str(value or "").replace(" ", "").casefold()


def build_pericia_raca_filter(column, racas):
    clauses = []
    params = []
    for raca in racas:
        key = _raca_sql_key(raca)
        if not key:
            continue
        clauses.append(f"(',' || REPLACE(LOWER({column}), ' ', '') || ',') LIKE ?")
        params.append(f"%,{key},%")
    if not clauses:
        return "1 = 0", ()
    return "(" + " OR ".join(clauses) + ")", tuple(params)


def get_pericia_race_inheritance_map(conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT raca_origem, raca_pericia
            FROM pericia_raca_heranca
            ORDER BY raca_origem COLLATE NOCASE, raca_pericia COLLATE NOCASE
            """
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        if owns_conn:
            conn.close()

    inheritance = {}
    for row in rows:
        source = _value(row, "raca_origem")
        target = _value(row, "raca_pericia", 1)
        inheritance.setdefault(_raca_key(source), []).append(target)
    return inheritance


def list_pericia_race_inheritance():
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT raca_origem, raca_pericia
            FROM pericia_raca_heranca
            ORDER BY raca_origem COLLATE NOCASE, raca_pericia COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def add_pericia_race_inheritance(raca_origem, racas_pericia):
    source = (raca_origem or "").strip()
    targets = split_raca_list(racas_pericia)
    if not source:
        return 0, targets
    if not targets:
        return 0, targets

    inserted = 0
    with get_connection() as conn:
        for target in targets:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO pericia_raca_heranca (raca_origem, raca_pericia)
                VALUES (?, ?)
                """,
                (source, target),
            )
            inserted += cursor.rowcount
        conn.commit()
    return inserted, targets


def remove_pericia_race_inheritance(raca_origem, raca_pericia=None):
    source = (raca_origem or "").strip()
    target = (raca_pericia or "").strip()
    if not source:
        return 0

    with get_connection() as conn:
        if target:
            cursor = conn.execute(
                """
                DELETE FROM pericia_raca_heranca
                WHERE raca_origem = ? COLLATE NOCASE
                  AND raca_pericia = ? COLLATE NOCASE
                """,
                (source, target),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM pericia_raca_heranca WHERE raca_origem = ? COLLATE NOCASE",
                (source,),
            )
        conn.commit()
    return cursor.rowcount


def get_accessible_pericia_racas(user_id, conn=None, base_raca=None):
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()

    racas = []
    seen = set()

    def add(raca):
        raca = (raca or "").strip()
        key = _raca_key(raca)
        if not key or key in seen:
            return
        seen.add(key)
        racas.append(raca)

    try:
        if base_raca is None:
            row = conn.execute("SELECT raca FROM personagens WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                base_raca = _value(row, "raca")

        sources = []
        if base_raca:
            sources.append(base_raca)

        vagas = conn.execute("SELECT vaga_nome FROM player_vagas WHERE user_id = ?", (user_id,)).fetchall()
        sources.extend(_value(vaga, "vaga_nome") for vaga in vagas)

        inheritance = get_pericia_race_inheritance_map(conn)
        pending = list(sources)
        while pending:
            source = pending.pop(0)
            add(source)
            for inherited in inheritance.get(_raca_key(source), ()):
                inherited_key = _raca_key(inherited)
                if inherited_key not in seen:
                    pending.append(inherited)
                add(inherited)

        add("Todas")
        return tuple(racas)
    finally:
        if owns_conn:
            conn.close()


def get_proximo_custo(nivel_atual):
    if nivel_atual >= MAX_PERICIA_LEVEL:
        return None
    return int(100 * (1.5 ** (nivel_atual - 1)))


def format_bonus(pericia):
    if pericia["bonus_valor"] is None or not pericia["atributo_afetado"]:
        return "Sem bônus"
    value = float(pericia["bonus_valor"])
    level_bonus = max(0, int(pericia["nivel"] or 1) - 1)
    attr = pericia["atributo_afetado"] or "atributo"
    normalized_attr = normalize_pericia_target(attr) or attr
    if normalized_attr.startswith("turnos:"):
        bonus_total = int(value * level_bonus)
        return f"+{bonus_total} turno(s) em {format_pericia_target(attr).replace('turnos de ', '')}"

    bonus_total = int(value * level_bonus * 100)
    return f"+{bonus_total}% em {format_pericia_target(attr)}"


def get_player_pericias(user_id):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        personagem = conn.execute(
            "SELECT nome, raca, pontos_pericia FROM personagens WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not personagem:
            return None

        racas = get_accessible_pericia_racas(user_id, conn, personagem["raca"])
        raca_filter, raca_params = build_pericia_raca_filter("pb.raca", racas)
        rows = conn.execute(
            f"""
            SELECT pb.id, pb.nome, pb.raca, pb.descricao, pb.bonus_valor,
                   pb.atributo_afetado, COALESCE(pp.nivel, 1) AS nivel,
                   COALESCE(pp.pp_investido, 0) AS pp_investido
            FROM pericias_base pb
            LEFT JOIN player_pericias pp ON pb.id = pp.pericia_id AND pp.user_id = ?
            WHERE {raca_filter}
            ORDER BY pb.nome COLLATE NOCASE
            """,
            (user_id, *raca_params),
        ).fetchall()

    pericias = []
    for row in rows:
        pericia = dict(row)
        custo = get_proximo_custo(pericia["nivel"])
        pericia["custo_proximo"] = custo
        pericia["bonus_atual"] = format_bonus(pericia)
        pericia["pp_necessario_restante"] = None if not custo else max(0, custo - pericia["pp_investido"])
        pericia["progresso_pp"] = 100 if not custo else min(100, int((pericia["pp_investido"] / custo) * 100))
        pericias.append(pericia)

    return {
        "user_id": user_id,
        "nome": personagem["nome"],
        "raca": personagem["raca"],
        "pontos_pericia": personagem["pontos_pericia"],
        "pericias": pericias,
    }


def investir_pericia(user_id, pericia_id, quantidade, return_details=False):
    try:
        quantidade = int(quantidade)
    except (TypeError, ValueError):
        result = (False, "Quantidade invalida.")
        return (*result, None) if return_details else result
    if quantidade <= 0:
        result = (False, "A quantidade deve ser maior que zero.")
        return (*result, None) if return_details else result

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        personagem = conn.execute(
            "SELECT raca, pontos_pericia FROM personagens WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not personagem:
            result = (False, "Personagem nao encontrado.")
            return (*result, None) if return_details else result

        racas = get_accessible_pericia_racas(user_id, conn, personagem["raca"])
        raca_filter, raca_params = build_pericia_raca_filter("pb.raca", racas)
        pericia = conn.execute(
            f"""
            SELECT pb.id, pb.nome, COALESCE(pp.nivel, 1) AS nivel,
                   COALESCE(pp.pp_investido, 0) AS pp_investido
            FROM pericias_base pb
            LEFT JOIN player_pericias pp ON pb.id = pp.pericia_id AND pp.user_id = ?
            WHERE pb.id = ? AND {raca_filter}
            """,
            (user_id, pericia_id, *raca_params),
        ).fetchone()
        if not pericia:
            result = (False, "Pericia indisponivel para este personagem.")
            return (*result, None) if return_details else result

        custo = get_proximo_custo(pericia["nivel"])
        if custo is None:
            result = (False, "Esta pericia ja esta no nivel maximo.")
            return (*result, None) if return_details else result
        if personagem["pontos_pericia"] < quantidade:
            result = (False, f"Voce possui apenas {personagem['pontos_pericia']} PP.")
            return (*result, None) if return_details else result

        restante = max(0, custo - pericia["pp_investido"])
        if quantidade > restante:
            result = (False, f"Esta pericia precisa de apenas {restante} PP para o proximo nivel.")
            return (*result, None) if return_details else result

        novo_investido = pericia["pp_investido"] + quantidade
        novo_nivel = pericia["nivel"]
        subiu = novo_investido >= custo
        if subiu:
            novo_nivel += 1
            novo_investido = 0

        conn.execute(
            "UPDATE personagens SET pontos_pericia = pontos_pericia - ? WHERE user_id = ?",
            (quantidade, user_id),
        )
        conn.execute(
            """
            INSERT INTO player_pericias (user_id, pericia_id, nivel, pp_investido)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, pericia_id) DO UPDATE
            SET nivel = excluded.nivel, pp_investido = excluded.pp_investido
            """,
            (user_id, pericia_id, novo_nivel, novo_investido),
        )
        conn.commit()

    details = {
        "pool_label": "PP disponíveis",
        "pool_before": personagem["pontos_pericia"],
        "pool_after": personagem["pontos_pericia"] - quantidade,
        "target_label": pericia["nome"],
        "target_before": f"Nv {pericia['nivel']} ({pericia['pp_investido']}/{custo})",
        "target_after": f"Nv {novo_nivel} ({novo_investido}/{get_proximo_custo(novo_nivel) or 'max'})",
    }
    if subiu:
        result = (True, f"{pericia['nome']} subiu para o nivel {novo_nivel}.")
        return (*result, details) if return_details else result
    result = (True, f"{quantidade} PP investidos em {pericia['nome']} ({novo_investido}/{custo}).")
    return (*result, details) if return_details else result


def subir_pericia(user_id, pericia_id):
    data = get_player_pericias(user_id)
    if not data:
        return False, "Personagem nao encontrado."
    pericia = next((p for p in data["pericias"] if p["id"] == pericia_id), None)
    if not pericia:
        return False, "Pericia indisponivel para este personagem."
    if pericia["custo_proximo"] is None:
        return False, "Esta pericia ja esta no nivel maximo."
    return investir_pericia(user_id, pericia_id, pericia["pp_necessario_restante"])
