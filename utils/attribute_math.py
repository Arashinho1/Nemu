PHYSICAL_ATTRIBUTES = ("forca", "velocidade", "resistencia")


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def non_passive_multiplier(bonus):
    if "non_passive_mult" in bonus:
        return _number(bonus.get("non_passive_mult"))
    return max(0.0, _number(bonus.get("mult")) - _number(bonus.get("passive_mult")))


def passive_attribute_value(base, bonus):
    base = _integer(base)
    passive_fixed = _integer(bonus.get("passive_fixo"))
    non_passive_fixed = (
        _integer(bonus.get("non_passive_fixo"))
        if "non_passive_fixo" in bonus
        else max(0, _integer(bonus.get("fixo")) - passive_fixed)
    )
    passive_mult = 1.0 + _number(bonus.get("passive_mult"))
    return int(((base + passive_fixed) * passive_mult) + non_passive_fixed)


def passive_attributes(base_values, vagas_bonus):
    return {
        attr: passive_attribute_value(base_values.get(attr, 0), vagas_bonus[attr])
        for attr in PHYSICAL_ATTRIBUTES
    }


def reiatsu_multiplier(vaga_forca_bonus, pericia_bonus, potencial_multiplier=1.0):
    return (
        1.0
        + non_passive_multiplier(vaga_forca_bonus)
        + _number(pericia_bonus.get("forca"))
        + _number(pericia_bonus.get("reiatsu"))
    ) * _number(potencial_multiplier, 1.0)
