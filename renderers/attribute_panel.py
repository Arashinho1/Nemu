from utils.profile_template import create_profile_card


def render_attribute_panel_desktop(user, character_data=None, avatar_bytes=None):
    return create_profile_card(character_data or {}, avatar_source=avatar_bytes)


def render_attribute_panel_mobile(user, character_data=None, avatar_bytes=None):
    return create_profile_card(character_data or {}, avatar_source=avatar_bytes, mobile=True)
