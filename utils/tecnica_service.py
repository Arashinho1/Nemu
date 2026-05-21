import sqlite3
import unicodedata

from database import get_connection, get_vagas_bonus, get_pericia_bonuses
from utils.attribute_math import passive_attributes
from utils.logic import calcular_reiryoku
from utils.pericia_service import get_accessible_pericia_racas, split_raca_list


PHYSICAL_ATTRIBUTES = ("forca", "velocidade", "resistencia")
TARGET_ALIASES = {
    "forca": "forca",
    "força": "forca",
    "velocidade": "velocidade",
    "resistencia": "resistencia",
    "resistência": "resistencia",
    "todos": "todos",
    "todas": "todos",
    "fisicos": "todos",
    "físicos": "todos",
}
CLASSIFICATION_LABELS = {
    "oficial": "Técnicas Oficiais",
    "criado": "Técnicas Criadas",
}


def normalize_classification(value):
    normalized = (value or "").lower().strip()
    if normalized in ("oficial", "oficiais", "sistema"):
        return "oficial"
    if normalized in ("criado", "criados", "criada", "criadas", "player", "jogador"):
        return "criado"
    return None


def _normalize_target(value):
    return TARGET_ALIASES.get((value or "").strip().lower())


def parse_targets(value):
    raw_targets = str(value or "todos").replace("+", ",").split(",")
    targets = []
    for raw in raw_targets:
        target = _normalize_target(raw)
        if not target:
            return None
        if target == "todos":
            return list(PHYSICAL_ATTRIBUTES)
        if target not in targets:
            targets.append(target)
    return targets or list(PHYSICAL_ATTRIBUTES)


def format_targets(value):
    targets = parse_targets(value)
    if not targets:
        return "inválido"
    if set(targets) == set(PHYSICAL_ATTRIBUTES):
        return "todos"
    return ", ".join(targets)


def _as_float(value, default=0.0):
    if value in (None, ""):
        return default
    return float(str(value).strip().replace(",", "."))


def _as_int(value, default=0):
    if value in (None, ""):
        return default
    return int(float(str(value).strip().replace(",", ".")))


def _text_key(value):
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return "".join(char for char in ascii_text.casefold() if char.isalnum())


def _raca_key(value):
    return _text_key(value)


def _role_id_set(role_ids):
    ids = set()
    for role_id in role_ids or ():
        try:
            ids.add(int(role_id))
        except (TypeError, ValueError):
            continue
    return ids


def _role_unlocked_tecnica_ids(conn, role_ids):
    ids = _role_id_set(role_ids)
    if not ids:
        return set()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT tecnica_id
        FROM tecnica_role_unlocks
        WHERE role_id IN ({placeholders})
        """,
        tuple(ids),
    ).fetchall()
    return {int(row[0]) for row in rows}


def _user_unlocked_tecnica_ids(conn, user_id):
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return set()
    rows = conn.execute(
        """
        SELECT tecnica_id
        FROM tecnica_user_unlocks
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchall()
    return {int(row[0]) for row in rows}


def _tecnica_raca_allowed(conn, tecnica, user_id):
    allowed_racas = split_raca_list(tecnica.get("raca"))
    if not allowed_racas:
        return True

    allowed_keys = {_raca_key(raca) for raca in allowed_racas}
    if "todas" in allowed_keys or "todos" in allowed_keys:
        return True

    accessible = get_accessible_pericia_racas(user_id, conn)
    accessible_keys = {_raca_key(raca) for raca in accessible}
    return bool(allowed_keys & accessible_keys)


def _tecnica_available_for_user(
    conn,
    tecnica,
    user_id,
    role_ids=None,
    role_unlocked_ids=None,
    user_unlocked_ids=None,
):
    if tecnica["classificacao"] == "criado":
        return tecnica["criador_id"] == user_id
    if tecnica["classificacao"] != "oficial":
        return False

    if user_unlocked_ids is None:
        user_unlocked_ids = _user_unlocked_tecnica_ids(conn, user_id)
    if tecnica["id"] in user_unlocked_ids:
        return True

    if role_unlocked_ids is None:
        role_unlocked_ids = _role_unlocked_tecnica_ids(conn, role_ids)
    if tecnica["id"] in role_unlocked_ids:
        return True
    if int(tecnica.get("liberada") if tecnica.get("liberada") is not None else 1) == 0:
        return False
    return _tecnica_raca_allowed(conn, tecnica, user_id)


def ensure_tecnica_state(user_id):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        char = conn.execute("SELECT 1 FROM personagens WHERE user_id = ?", (user_id,)).fetchone()
        if not char:
            return None
        state = conn.execute("SELECT * FROM tecnica_estado WHERE user_id = ?", (user_id,)).fetchone()
        if not state:
            conn.execute("INSERT INTO tecnica_estado (user_id) VALUES (?)", (user_id,))
            conn.commit()
            state = conn.execute("SELECT * FROM tecnica_estado WHERE user_id = ?", (user_id,)).fetchone()
    return dict(state)


def create_tecnica(nome, categoria, classificacao, criador_id=None, descricao=""):
    nome = (nome or "").strip()
    categoria = (categoria or "").strip()
    descricao = (descricao or "").strip()
    class_label = normalize_classification(classificacao)

    if not nome:
        return False, "Nome da técnica não pode ficar vazio.", None
    if not categoria:
        return False, "Categoria da técnica não pode ficar vazia.", None
    if not class_label:
        return False, "Classificação inválida. Use oficial ou criado.", None
    if class_label == "criado" and not criador_id:
        return False, "Técnica criada precisa de um criador.", None

    with get_connection() as conn:
        duplicate = conn.execute(
            """
            SELECT id
            FROM tecnicas
            WHERE LOWER(nome) = LOWER(?)
              AND LOWER(categoria) = LOWER(?)
              AND classificacao = ?
              AND COALESCE(criador_id, 0) = COALESCE(?, 0)
            """,
            (nome, categoria, class_label, criador_id),
        ).fetchone()
        if duplicate:
            return False, f"Técnica já cadastrada com ID {duplicate[0]}.", duplicate[0]

        cursor = conn.execute(
            """
            INSERT INTO tecnicas (nome, categoria, classificacao, criador_id, descricao)
            VALUES (?, ?, ?, ?, ?)
            """,
            (nome, categoria, class_label, criador_id, descricao),
        )
        conn.commit()
        tecnica_id = cursor.lastrowid

    return True, "Técnica registrada.", tecnica_id


def list_tecnicas(classificacao=None, user_id=None, include_private=False):
    class_label = normalize_classification(classificacao) if classificacao else None
    query = """
        SELECT id, nome, categoria, classificacao, criador_id, descricao,
               multiplicador, bonus_fixo, atributo, duracao, cooldown,
               raca, requer_pericia, liberada
        FROM tecnicas
        WHERE 1 = 1
    """
    params = []
    if class_label:
        query += " AND classificacao = ?"
        params.append(class_label)
    if class_label == "criado" and not include_private:
        query += " AND criador_id = ?"
        params.append(user_id)
    query += " ORDER BY classificacao, categoria COLLATE NOCASE, nome COLLATE NOCASE"

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def list_available_tecnicas(user_id, classificacao, role_ids=None):
    class_label = normalize_classification(classificacao)
    if class_label == "criado":
        return list_tecnicas("criado", user_id=user_id, include_private=False)
    if class_label == "oficial":
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, nome, categoria, classificacao, criador_id, descricao,
                       multiplicador, bonus_fixo, atributo, duracao, cooldown,
                       raca, requer_pericia, liberada
                FROM tecnicas
                WHERE classificacao = 'oficial'
                ORDER BY categoria COLLATE NOCASE, nome COLLATE NOCASE
                """
            ).fetchall()
            role_unlocked_ids = _role_unlocked_tecnica_ids(conn, role_ids)
            user_unlocked_ids = _user_unlocked_tecnica_ids(conn, user_id)
            return [
                dict(row)
                for row in rows
                if _tecnica_available_for_user(
                    conn,
                    dict(row),
                    user_id,
                    role_ids,
                    role_unlocked_ids,
                    user_unlocked_ids,
                )
            ]
    return []


def get_tecnica(tecnica_id, user_id=None, role_ids=None):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, nome, categoria, classificacao, criador_id, descricao,
                   multiplicador, bonus_fixo, atributo, duracao, cooldown,
                   raca, requer_pericia, liberada
            FROM tecnicas
            WHERE id = ?
            """,
            (tecnica_id,),
        ).fetchone()
        if not row:
            return None
        tecnica = dict(row)
        if user_id is None:
            return tecnica
        if _tecnica_available_for_user(conn, tecnica, user_id, role_ids):
            return tecnica
        return None


def find_tecnica_by_name(nome, classificacao="oficial"):
    wanted = _text_key(nome)
    if not wanted:
        return None
    tecnicas = list_tecnicas(classificacao, include_private=True)
    exact = [tecnica for tecnica in tecnicas if _text_key(tecnica["nome"]) == wanted]
    if exact:
        return exact[0]
    partial = [tecnica for tecnica in tecnicas if wanted in _text_key(tecnica["nome"])]
    return partial[0] if len(partial) == 1 else None


def grant_tecnica_to_role(nome, role_id):
    tecnica = find_tecnica_by_name(nome, "oficial")
    if not tecnica:
        return False, "Técnica oficial não encontrada pelo nome informado.", None
    try:
        role_id = int(role_id)
    except (TypeError, ValueError):
        return False, "Cargo inválido.", None

    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO tecnica_role_unlocks (tecnica_id, role_id)
            VALUES (?, ?)
            """,
            (tecnica["id"], role_id),
        )
        conn.commit()
    return True, f"Técnica `{tecnica['nome']}` liberada para o cargo.", tecnica["id"]


def grant_tecnica_to_user(nome, user_id):
    tecnica = find_tecnica_by_name(nome, "oficial")
    if not tecnica:
        return False, "Técnica oficial não encontrada pelo nome informado.", None
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return False, "Player inválido.", None

    with get_connection() as conn:
        char = conn.execute("SELECT 1 FROM personagens WHERE user_id = ?", (user_id,)).fetchone()
        if not char:
            return False, "Este player não possui personagem cadastrado.", None
        conn.execute(
            """
            INSERT OR IGNORE INTO tecnica_user_unlocks (tecnica_id, user_id)
            VALUES (?, ?)
            """,
            (tecnica["id"], user_id),
        )
        conn.commit()
    return True, f"Técnica `{tecnica['nome']}` liberada para o player.", tecnica["id"]


def configure_tecnica_buff(tecnica_id, multiplicador, bonus_fixo, atributo, duracao=1, cooldown=1):
    try:
        mult = _as_float(multiplicador, 0.0)
        fixo = _as_int(bonus_fixo, 0)
        dur = max(1, _as_int(duracao, 1))
        cd = max(0, _as_int(cooldown, 1))
    except (TypeError, ValueError):
        return False, "Valores inválidos para buff, duração ou cooldown.", None

    if mult < 0 or fixo < 0:
        return False, "Buffs não podem ser negativos.", None
    targets = parse_targets(atributo)
    if not targets:
        return False, "Atributo inválido. Use forca, velocidade, resistencia ou todos.", None
    attr_value = "todos" if set(targets) == set(PHYSICAL_ATTRIBUTES) else ",".join(targets)

    with get_connection() as conn:
        row = conn.execute("SELECT nome FROM tecnicas WHERE id = ?", (tecnica_id,)).fetchone()
        if not row:
            return False, "Técnica não encontrada.", None
        conn.execute(
            """
            UPDATE tecnicas
            SET multiplicador = ?, bonus_fixo = ?, atributo = ?, duracao = ?, cooldown = ?
            WHERE id = ?
            """,
            (mult, fixo, attr_value, dur, cd, tecnica_id),
        )
        conn.commit()
    return True, f"Buff de `{row[0]}` configurado.", tecnica_id


def tecnica_has_buff(tecnica):
    return bool((tecnica.get("multiplicador") or 0) > 0 or (tecnica.get("bonus_fixo") or 0) > 0)


def get_tecnica_passive_bonus(user_id, tecnica):
    tecnica_keys = {
        _text_key(tecnica.get("nome")),
        _text_key(tecnica.get("categoria")),
        _text_key(tecnica.get("requer_pericia")),
    }
    tecnica_keys.discard("")

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT pb.atributo_afetado, pb.bonus_valor, pp.nivel
            FROM player_pericias pp
            JOIN pericias_base pb ON pp.pericia_id = pb.id
            WHERE pp.user_id = ?
              AND pb.bonus_valor IS NOT NULL
              AND pb.atributo_afetado IS NOT NULL
            """,
            (user_id,),
        ).fetchall()

    total = 0.0
    for atributo_afetado, bonus_valor, nivel in rows:
        target = str(atributo_afetado or "").strip()
        if not target.lower().startswith("tecnica:"):
            continue
        target_key = _text_key(target.split(":", 1)[1])
        if target_key in tecnica_keys:
            total += float(bonus_valor) * (int(nivel) - 1)
    return total


def get_tecnica_turn_bonus(user_id, tecnica_nome):
    target_key = _text_key(tecnica_nome)
    if not target_key:
        return 0

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT pb.atributo_afetado, pb.bonus_valor, pp.nivel
            FROM player_pericias pp
            JOIN pericias_base pb ON pp.pericia_id = pb.id
            WHERE pp.user_id = ?
              AND pb.bonus_valor IS NOT NULL
              AND pb.atributo_afetado IS NOT NULL
            """,
            (user_id,),
        ).fetchall()

    total = 0
    for atributo_afetado, bonus_valor, nivel in rows:
        target = str(atributo_afetado or "").strip()
        if not target.lower().startswith("turnos:"):
            continue
        if _text_key(target.split(":", 1)[1]) == target_key:
            total += int(float(bonus_valor) * (int(nivel) - 1))
    return total


def use_tecnica(user_id, tecnica_id, role_ids=None):
    state = ensure_tecnica_state(user_id)
    if not state:
        return False, "Personagem não encontrado.", None
    if state["cooldown"] > 0:
        return False, f"Suas técnicas estão em cooldown por mais {state['cooldown']} turno(s).", None

    tecnica = get_tecnica(tecnica_id, user_id, role_ids)
    if not tecnica:
        return False, "Técnica indisponível para este usuário.", None
    if not tecnica_has_buff(tecnica):
        return False, "Esta técnica ainda não possui buff configurado pela staff em `.buffar`.", None

    targets = parse_targets(tecnica.get("atributo"))
    if not targets:
        return False, "Atributos configurados nesta técnica são inválidos.", None

    mult = float(tecnica.get("multiplicador") or 0.0)
    fixo = int(tecnica.get("bonus_fixo") or 0)
    duracao = max(1, int(tecnica.get("duracao") or 1))
    turn_bonus = get_tecnica_turn_bonus(user_id, tecnica["nome"])
    if turn_bonus > 0:
        duracao += turn_bonus
    cooldown = max(0, int(tecnica.get("cooldown") or 0))
    passive_bonus = get_tecnica_passive_bonus(user_id, tecnica)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tecnica_usos (user_id, tecnica_id, nome, atributo, multiplicador, bonus_fixo, duracao, cooldown)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, tecnica["id"], tecnica["nome"], ",".join(targets), mult, fixo, duracao, cooldown),
        )
        uso_id = cursor.lastrowid
        for attr in targets:
            if fixo > 0:
                conn.execute(
                    """
                    INSERT INTO attribute_modifiers
                        (user_id, atributo, nome, tipo, valor, origem, ativo, tecnica_uso_id, turnos_restantes)
                    VALUES (?, ?, ?, 'flat', ?, 'tecnica', 1, ?, ?)
                    """,
                    (user_id, attr, tecnica["nome"], fixo, uso_id, duracao),
                )
            if mult > 0:
                conn.execute(
                    """
                    INSERT INTO attribute_modifiers
                        (user_id, atributo, nome, tipo, valor, origem, ativo, tecnica_uso_id, turnos_restantes)
                    VALUES (?, ?, ?, 'percent', ?, 'tecnica', 1, ?, ?)
                    """,
                    (user_id, attr, tecnica["nome"], round(mult * 100, 2), uso_id, duracao),
                )
        conn.execute(
            """
            UPDATE tecnica_estado
            SET cooldown = ?, usos_total = usos_total + 1, ultimo_tecnica = ?
            WHERE user_id = ?
            """,
            (cooldown, tecnica["nome"], user_id),
        )
        conn.commit()

    data = {
        "tecnica": tecnica,
        "targets": targets,
        "multiplicador": mult,
        "bonus_fixo": fixo,
        "pericia_bonus": passive_bonus,
        "turn_bonus": turn_bonus,
        "duracao": duracao,
        "cooldown": cooldown,
        "state": ensure_tecnica_state(user_id),
    }
    return True, "Técnica usada.", data

def use_hollow_regen(user_id):
    """Processa a regeneração Hollow baseada em Tiers da perícia Regen."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        char = conn.execute("SELECT raca, forca, velocidade, resistencia FROM personagens WHERE user_id = ?", (user_id,)).fetchone()
        if not char:
            return False, "Personagem não encontrado.", None

        # Validação de Raça
        raca_low = (char['raca'] or "").lower()
        allowed = ["hollow", "arrancar", "vaizard", "vizard", "visored"]
        if not any(sub in raca_low for sub in allowed):
            return False, "Apenas Hollows, Arrancars ou Vaizards possuem Regeneração Instantânea.", None

        # Busca nível da perícia Regen
        pericia = conn.execute("""
            SELECT pp.nivel FROM player_pericias pp
            JOIN pericias_base pb ON pp.pericia_id = pb.id
            WHERE pp.user_id = ? AND pb.nome = 'Regen'
        """, (user_id,)).fetchone()
        
        nivel = pericia['nivel'] if pericia else 1
        
        # Definição de Tiers (I-II, III-IV, V-VI)
        if nivel <= 2:
            percent, mult, tier_label = 0.05, 1.50, "I/II"
        elif nivel <= 4:
            percent, mult, tier_label = 0.10, 1.35, "III/IV"
        else:
            percent, mult, tier_label = 0.15, 1.25, "V/VI"

        # Cálculo de Reiryoku Máximo (Atributos + Bônus)
        v_bonuses = get_vagas_bonus(user_id)
        p_bonuses = get_pericia_bonuses(user_id)
        permanent_attrs = passive_attributes(
            {
                "forca": char['forca'],
                "velocidade": char['velocidade'],
                "resistencia": char['resistencia'],
            },
            v_bonuses,
        )
        r_base = calcular_reiryoku(
            permanent_attrs["forca"],
            permanent_attrs["velocidade"],
            permanent_attrs["resistencia"],
        )
        r_max = int(r_base * (1.0 + p_bonuses.get("reiryoku", 0.0)))

        # Status atual (tabela kido_estado centraliza a energia atual)
        state = conn.execute("SELECT reiryoku_atual, cooldown FROM kido_estado WHERE user_id = ?", (user_id,)).fetchone()
        if not state:
            conn.execute("INSERT INTO kido_estado (user_id, reiryoku_atual) VALUES (?, ?)", (user_id, r_max))
            curr_reiryoku, cd = r_max, 0
        else:
            curr_reiryoku, cd = state['reiryoku_atual'], state['cooldown']

        if cd > 0:
            return False, f"Você está em exaustão espiritual por mais {cd} turno(s).", None

        heal_amount = int(r_max * percent)
        cost = int(heal_amount * mult)

        if curr_reiryoku < cost:
            return False, f"Energia insuficiente. Custo: {cost} | Atual: {curr_reiryoku}", None

        final_reiryoku = min(r_max, curr_reiryoku - cost + heal_amount)
        conn.execute("UPDATE kido_estado SET reiryoku_atual = ?, cooldown = 0 WHERE user_id = ?", (final_reiryoku, user_id))
        conn.commit()

        return True, "Sucesso", {"tier": tier_label, "cost": cost, "heal": heal_amount, "current": final_reiryoku, "max": r_max}
