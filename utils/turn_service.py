import sqlite3

from database import get_connection
from utils.kido_service import ensure_kido_state


def advance_player_turn(user_id):
    updates = []

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        potentials = conn.execute(
            """
            SELECT pp.potencial, pp.ativo, pp.turnos, pp.cooldown, pp.cd_mod,
                   p.cooldown AS base_cooldown, p.custo_turno
            FROM player_potencial pp
            LEFT JOIN potenciais p ON pp.potencial = p.nome
            WHERE pp.user_id = ?
              AND (pp.ativo = 1 OR pp.cooldown > 0)
            ORDER BY pp.potencial COLLATE NOCASE
            """,
            (user_id,),
        ).fetchall()

        reiryoku_state = ensure_kido_state(user_id)

        for row in potentials:
            nome = row["potencial"]
            if row["ativo"] == 1 and row["turnos"] > 0:
                custo_turno = max(0, row["custo_turno"] or 0)
                if custo_turno > 0:
                    if not reiryoku_state:
                        updates.append(
                            {
                                "name": nome,
                                "type": "Potencial",
                                "status": "Erro",
                                "remaining": 0,
                                "text": f"`{nome}` nao teve consumo calculado porque o personagem nao foi encontrado.",
                            }
                        )
                        continue

                    if reiryoku_state["reiryoku_atual"] < custo_turno:
                        next_cd = max(0, (row["base_cooldown"] or 0) + (row["cd_mod"] or 0))
                        conn.execute(
                            """
                            UPDATE player_potencial
                            SET ativo = 0, turnos = 0, cooldown = ?
                            WHERE user_id = ? AND potencial = ?
                            """,
                            (next_cd, user_id, nome),
                        )
                        updates.append(
                            {
                                "name": nome,
                                "type": "Potencial",
                                "status": "Sem Reiryoku",
                                "remaining": next_cd,
                                "text": (
                                    f"`{nome}` encerrou por Reiryoku insuficiente "
                                    f"(`{reiryoku_state['reiryoku_atual']}/{custo_turno}`) e entrou em recarga por `{next_cd}` turno(s)."
                                ),
                            }
                        )
                        continue

                    novo_reiryoku = reiryoku_state["reiryoku_atual"] - custo_turno
                    conn.execute(
                        "UPDATE kido_estado SET reiryoku_atual = ? WHERE user_id = ?",
                        (novo_reiryoku, user_id),
                    )
                    reiryoku_state["reiryoku_atual"] = novo_reiryoku

                remaining = max(0, row["turnos"] - 1)
                if remaining == 0:
                    next_cd = max(0, (row["base_cooldown"] or 0) + (row["cd_mod"] or 0))
                    conn.execute(
                        """
                        UPDATE player_potencial
                        SET ativo = 0, turnos = 0, cooldown = ?
                        WHERE user_id = ? AND potencial = ?
                        """,
                        (next_cd, user_id, nome),
                    )
                    updates.append(
                        {
                            "name": nome,
                            "type": "Potencial",
                            "status": "Encerrado",
                            "remaining": next_cd,
                            "text": (
                                f"`{nome}` encerrou e entrou em recarga por `{next_cd}` turno(s)."
                                + (f" Consumo: `{custo_turno}` Reiryoku." if custo_turno > 0 else "")
                            ),
                        }
                    )
                else:
                    conn.execute(
                        "UPDATE player_potencial SET turnos = ? WHERE user_id = ? AND potencial = ?",
                        (remaining, user_id, nome),
                    )
                    updates.append(
                        {
                            "name": nome,
                            "type": "Potencial",
                            "status": "Ativo",
                            "remaining": remaining,
                            "text": (
                                f"`{nome}` permanece ativo por `{remaining}` turno(s)."
                                + (
                                    f" Consumo: `{custo_turno}` Reiryoku (`{reiryoku_state['reiryoku_atual']}/{reiryoku_state['reiryoku_max']}`)."
                                    if custo_turno > 0 and reiryoku_state
                                    else ""
                                )
                            ),
                        }
                    )
            elif row["cooldown"] > 0:
                remaining = max(0, row["cooldown"] - 1)
                conn.execute(
                    "UPDATE player_potencial SET cooldown = ? WHERE user_id = ? AND potencial = ?",
                    (remaining, user_id, nome),
                )
                text = (
                    f"`{nome}` está pronto para uso."
                    if remaining == 0
                    else f"Restam `{remaining}` turno(s) para `{nome}`."
                )
                updates.append(
                    {
                        "name": nome,
                        "type": "Potencial",
                        "status": "Pronto" if remaining == 0 else "Recarga",
                        "remaining": remaining,
                        "text": text,
                    }
                )

        kido = conn.execute("SELECT cooldown FROM kido_estado WHERE user_id = ?", (user_id,)).fetchone()
        if kido and kido["cooldown"] > 0:
            remaining = max(0, kido["cooldown"] - 1)
            conn.execute("UPDATE kido_estado SET cooldown = ? WHERE user_id = ?", (remaining, user_id))
            text = (
                "`Kidō` está pronto para uso."
                if remaining == 0
                else f"Restam `{remaining}` turno(s) para `Kidō`."
            )
            updates.append(
                {
                    "name": "Kidō",
                    "type": "Kidō",
                    "status": "Pronto" if remaining == 0 else "Recarga",
                    "remaining": remaining,
                    "text": text,
                }
            )

        tecnica = conn.execute("SELECT cooldown FROM tecnica_estado WHERE user_id = ?", (user_id,)).fetchone()
        if tecnica and tecnica["cooldown"] > 0:
            remaining = max(0, tecnica["cooldown"] - 1)
            conn.execute("UPDATE tecnica_estado SET cooldown = ? WHERE user_id = ?", (remaining, user_id))
            text = (
                "`Técnicas` estão prontas para uso."
                if remaining == 0
                else f"Restam `{remaining}` turno(s) para `Técnicas`."
            )
            updates.append(
                {
                    "name": "Técnicas",
                    "type": "Técnica",
                    "status": "Pronto" if remaining == 0 else "Recarga",
                    "remaining": remaining,
                    "text": text,
                }
            )

        tecnicas_ativas = conn.execute(
            """
            SELECT tecnica_uso_id, nome, MIN(turnos_restantes) AS turnos
            FROM attribute_modifiers
            WHERE user_id = ? AND origem = 'tecnica' AND ativo = 1 AND turnos_restantes IS NOT NULL
            GROUP BY tecnica_uso_id, nome
            ORDER BY tecnica_uso_id
            """,
            (user_id,),
        ).fetchall()
        for row in tecnicas_ativas:
            remaining = max(0, (row["turnos"] or 0) - 1)
            if remaining == 0:
                conn.execute(
                    """
                    UPDATE attribute_modifiers
                    SET ativo = 0, turnos_restantes = 0
                    WHERE user_id = ? AND origem = 'tecnica' AND tecnica_uso_id = ?
                    """,
                    (user_id, row["tecnica_uso_id"]),
                )
                updates.append(
                    {
                        "name": row["nome"],
                        "type": "Técnica",
                        "status": "Encerrada",
                        "remaining": 0,
                        "text": f"`{row['nome']}` encerrou e seus buffs físicos foram removidos.",
                    }
                )
            else:
                conn.execute(
                    """
                    UPDATE attribute_modifiers
                    SET turnos_restantes = ?
                    WHERE user_id = ? AND origem = 'tecnica' AND tecnica_uso_id = ?
                    """,
                    (remaining, user_id, row["tecnica_uso_id"]),
                )
                updates.append(
                    {
                        "name": row["nome"],
                        "type": "Técnica",
                        "status": "Ativa",
                        "remaining": remaining,
                        "text": f"`{row['nome']}` permanece ativo por `{remaining}` turno(s).",
                    }
                )

        conn.commit()

    return updates
